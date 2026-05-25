import "../core/env.js";
import { createTier1ExchangeApp } from "../app.js";
import type { DomainEvent } from "../core/types.js";
import { ValuationService } from "../services/valuationService.js";
import { TreasuryOnChainService } from "../services/treasuryOnChainService.js";

type StressCase =
  | {
      kind: "swap";
      fromToken: "NENO";
      toToken: "USDT" | "WBNB";
      amount: string;
    }
  | {
      kind: "offramp";
      fromToken: "NENO";
      fiatCurrency: "EUR";
      amount: string;
      rate: string;
    };

interface StressResult {
  caseId: string;
  transactionId: string;
  kind: StressCase["kind"];
  target: string;
  amount: string;
  status: "settlement_confirmed" | "settlement_pending_confirmation" | "failed";
  classification?: "INSUFFICIENT_LIQUIDITY" | "GAS_REVERT" | "MIN_OUT_NOT_MET" | "SETTLEMENT_TIMEOUT" | "UNKNOWN";
  txHash?: string;
  settlementId?: string;
  integrity: boolean;
  state: string;
  eventTypes: string[];
  errors: string[];
}

const swapAmounts = ["1", "5", "10", "25", "50"];
const offrampAmounts = ["1", "2", "5", "10"];

async function main(): Promise<void> {
  const app = createTier1ExchangeApp();
  await assertProductionExecutionReady(app);
  await app.store.ready();
  const valuation = new ValuationService();
  const cases: StressCase[] = [
    ...swapAmounts.flatMap((amount) => [
      { kind: "swap" as const, fromToken: "NENO" as const, toToken: "USDT" as const, amount },
      { kind: "swap" as const, fromToken: "NENO" as const, toToken: "WBNB" as const, amount },
    ]),
    ...offrampAmounts.map((amount) => ({
      kind: "offramp" as const,
      fromToken: "NENO" as const,
      fiatCurrency: "EUR" as const,
      amount,
      rate: "20000",
    })),
  ];

  const submitted = await Promise.all(
    cases.map(async (testCase, index) => {
      const idempotencyKey = `stress-real-${Date.now()}-${index}-${testCase.kind}-${testCase.amount}`;
      if (testCase.kind === "swap") {
        const swapValuation = await valuation.swapNenoToAsset(testCase.amount, testCase.toToken);
        const order = await app.orderService.createIntent({
          idempotencyKey,
          accountId: process.env.STRESS_TEST_USER_ID ?? "massi-prod-001",
          type: "swap",
          fromAsset: testCase.fromToken,
          toAsset: testCase.toToken,
          fromAmount: testCase.amount,
          expectedToAmount: swapValuation.targetAmount,
          provider: "real",
          metadata: {
            valuation: swapValuation,
            slippageBps: process.env.STRESS_SWAP_SLIPPAGE_BPS ?? process.env.SWAP_SLIPPAGE_BPS,
          },
        });
        return { caseId: `${testCase.kind}:${testCase.amount}:${testCase.toToken}`, testCase, transactionId: order.transactionId };
      }

      const offrampValuation = valuation.offrampNenoToFiatEquivalent(testCase.amount, testCase.rate, testCase.fiatCurrency);
      const order = await app.orderService.createIntent({
        idempotencyKey,
        accountId: process.env.STRESS_TEST_USER_ID ?? "massi-prod-001",
        type: "offramp",
        fromAsset: testCase.fromToken,
        toAsset: testCase.fiatCurrency,
        fromAmount: testCase.amount,
        expectedToAmount: offrampValuation.targetAmount,
        provider: "real",
        metadata: {
          rate: testCase.rate,
          valuation: offrampValuation,
        },
      });
      return { caseId: `${testCase.kind}:${testCase.amount}:${testCase.fiatCurrency}`, testCase, transactionId: order.transactionId };
    }),
  );

  const timeoutMs = Number(process.env.STRESS_SETTLEMENT_TIMEOUT_MS ?? 180_000);
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await app.bus.drain();
    const allTerminal = submitted.every(({ transactionId }) => {
      const events = app.store.events.byTransaction(transactionId);
      return (
        events.some((event) => event.type === "settlement.confirmed") ||
        events.some((event) => event.type === "settlement.failed") ||
        events.some((event) => event.type === "execution.failed")
      );
    });
    if (allTerminal) break;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  const results: StressResult[] = [];
  for (const item of submitted) {
    await app.bus.drain();
    results.push(await summarize(app, item.caseId, item.testCase, item.transactionId));
  }

  const invariantViolations = results.filter(
    (result) => result.status === "settlement_confirmed" && (!result.integrity || !result.eventTypes.includes("execution.completed")),
  );
  const unclassifiedFailures = results.filter((result) => result.status !== "settlement_confirmed" && !result.classification);
  console.log(
    JSON.stringify(
      {
        startedAt: new Date().toISOString(),
        cases: cases.length,
        confirmed: results.filter((result) => result.status === "settlement_confirmed").length,
        failed: results.filter((result) => result.status === "failed").length,
        pending: results.filter((result) => result.status === "settlement_pending_confirmation").length,
        invariantValid: invariantViolations.length === 0 && unclassifiedFailures.length === 0,
        results,
      },
      null,
      2,
    ),
  );
  if (invariantViolations.length > 0 || unclassifiedFailures.length > 0) {
    process.exitCode = 1;
  }
}

async function summarize(
  app: ReturnType<typeof createTier1ExchangeApp>,
  caseId: string,
  testCase: StressCase,
  transactionId: string,
): Promise<StressResult> {
  const report = await app.reconciliationEngine.reconcile(transactionId);
  await app.bus.drain();
  const events = app.store.events.byTransaction(transactionId);
  const initiated = events.find((event) => event.type === "settlement.initiated");
  const failure = events.find((event) => event.type === "execution.failed" || event.type === "settlement.failed");
  const confirmed = events.find((event) => event.type === "settlement.confirmed");
  const pending = events.find((event) => event.type === "settlement.pending_confirmation");
  return {
    caseId,
    transactionId,
    kind: testCase.kind,
    target: testCase.kind === "swap" ? testCase.toToken : testCase.fiatCurrency,
    amount: testCase.amount,
    status: confirmed ? "settlement_confirmed" : failure ? "failed" : pending ? "settlement_pending_confirmation" : "failed",
    classification: confirmed ? undefined : classifyFailure(events),
    txHash: stringPayload(initiated, "txHash"),
    settlementId: stringPayload(initiated, "settlementId"),
    integrity: report.integrity,
    state: report.state,
    eventTypes: events.map((event) => event.type),
    errors: report.errors,
  };
}

function classifyFailure(events: DomainEvent[]): StressResult["classification"] {
  const reason = events
    .filter((event) => event.type === "execution.failed" || event.type === "settlement.failed")
    .map((event) => `${String(event.payload.reason ?? "")} ${String(event.payload.error ?? "")}`)
    .join(" ");
  if (/quote below protected minOut|minOut/i.test(reason)) return "MIN_OUT_NOT_MET";
  if (/REJECTED_INSUFFICIENT_LIQUIDITY|liquidity/i.test(reason)) return "INSUFFICIENT_LIQUIDITY";
  if (/OFFRAMP_PREFLIGHT_FAILED|revert|CALL_EXCEPTION|estimateGas|execution reverted/i.test(reason)) return "GAS_REVERT";
  if (/SETTLEMENT_TIMEOUT|timeout|not reached|pending|confirmations/i.test(reason)) return "SETTLEMENT_TIMEOUT";
  if (events.some((event) => event.type === "settlement.pending_confirmation")) return "SETTLEMENT_TIMEOUT";
  return "UNKNOWN";
}

function stringPayload(event: DomainEvent | undefined, key: string): string | undefined {
  const value = event?.payload[key];
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

async function assertProductionExecutionReady(app: ReturnType<typeof createTier1ExchangeApp>): Promise<void> {
  const report = app.productionPreflightService.report("all") as {
    checks: Array<{ name: string; ok: boolean; detail: string }>;
  };
  const failed = report.checks.filter((check) => !check.ok);
  if (failed.length > 0) {
    throw new Error(`Production execution preflight failed: ${failed.map((check) => `${check.name}(${check.detail})`).join(", ")}`);
  }
  const treasury = await new TreasuryOnChainService(app.assetRegistry).balances();
  if (!Boolean((treasury as { fundingSufficientForConfiguredBatch?: boolean }).fundingSufficientForConfiguredBatch)) {
    throw new Error(`Production execution funding failed: ${JSON.stringify(treasury)}`);
  }
}

main().catch((error) => {
  console.error(JSON.stringify({ level: "error", component: "stress-real-flows", error: error instanceof Error ? error.message : String(error) }));
  process.exitCode = 1;
});
