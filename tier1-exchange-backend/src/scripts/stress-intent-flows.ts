import "../core/env.js";
import { createTier1ExchangeApp } from "../app.js";
import { ValuationService } from "../services/valuationService.js";
import { TreasuryOnChainService } from "../services/treasuryOnChainService.js";
import { ExecutionReadinessController } from "../services/executionReadinessController.js";
import { RFQAggregator } from "../services/rfqAggregator.js";

const SWAP_SIZES = ["50", "100", "500", "1000", "5000", "10000", "20000", "50000", "100000", "200000"];
const OUTPUTS = ["USDT", "USDC", "WBNB", "ETH", "BTC"] as const;
const OFFRAMP_LADDER = ["100", "500", "1000", "5000", "10000", "20000"];

interface IntentStressResult {
  intentId: string;
  type: "swap" | "offramp";
  amount: string;
  target: string;
  route: string[];
  twap: boolean;
  eventTypes: string[];
  status: "settlement.confirmed" | "settlement.failed" | "execution.failed" | "pending";
  integrity: boolean;
  errors: string[];
}

async function main(): Promise<void> {
  const app = createTier1ExchangeApp();
  await assertProductionExecutionReady(app);
  await app.store.ready();
  const valuation = new ValuationService();
  const totalSwapIntents = Number(process.env.INTENT_STRESS_SWAP_COUNT ?? 100);
  const submitted: Array<{ intentId: string; type: "swap" | "offramp"; amount: string; target: string; route: string[]; twap: boolean; retryOf?: string }> = [];

  const swapSubmissions = Array.from({ length: totalSwapIntents }, async (_, index) => {
    const amount = SWAP_SIZES[index % SWAP_SIZES.length];
    const target = OUTPUTS[index % OUTPUTS.length];
    const swapValuation = await valuation.swapNenoToAsset(amount, target);
    const intent = await app.intentService.createSwapIntent({
      idempotencyKey: `intent-stress-swap-${Date.now()}-${index}`,
      accountId: process.env.STRESS_TEST_USER_ID ?? "massi-prod-001",
      fromAsset: "NENO",
      toAsset: target,
      amount,
      expectedToAmount: swapValuation.targetAmount,
      provider: "real",
      metadata: {
        valuation: swapValuation,
      },
    });
    return { intentId: intent.intentId, type: "swap" as const, amount, target, route: intent.route, twap: intent.twap };
  });

  const offrampSubmissions = OFFRAMP_LADDER.map(async (amount, index) => {
    const rate = process.env.NENO_USDT_RATE ?? "20000";
    const offrampValuation = valuation.offrampNenoToFiatEquivalent(amount, rate, "EUR");
    const intent = await app.intentService.createOfframpIntent({
      idempotencyKey: `intent-stress-offramp-${Date.now()}-${index}`,
      accountId: process.env.STRESS_TEST_USER_ID ?? "massi-prod-001",
      fromAsset: "NENO",
      fiatCurrency: "EUR",
      amount,
      expectedFiatAmount: offrampValuation.targetAmount,
      provider: "real",
      metadata: {
        rate,
        valuation: offrampValuation,
      },
    });
    return { intentId: intent.intentId, type: "offramp" as const, amount, target: "EUR", route: intent.route, twap: intent.twap };
  });

  submitted.push(...(await Promise.all([...swapSubmissions, ...offrampSubmissions])));
  await app.bus.drain();

  const deadline = Date.now() + Number(process.env.INTENT_STRESS_TIMEOUT_MS ?? 900_000);
  while (Date.now() < deadline) {
    await app.bus.drain();
    if (submitted.every((item) => terminal(app.store.events.byTransaction(item.intentId)))) break;
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }

  let results: IntentStressResult[] = [];
  for (const item of submitted) {
    const report = await app.reconciliationEngine.reconcile(item.intentId);
    await app.bus.drain();
    const events = app.store.events.byTransaction(item.intentId);
    results.push({
      ...item,
      eventTypes: events.map((event) => event.type),
      status: statusFor(events),
      integrity: report.integrity,
      errors: report.errors,
    });
  }

  const retryBudget = Number(process.env.INTENT_STRESS_RETRY_PASSES ?? 1);
  for (let retryPass = 1; retryPass <= retryBudget; retryPass += 1) {
    const retryable = results.filter((result) => result.status !== "settlement.confirmed" && result.status !== "pending");
    if (retryable.length === 0) break;
    console.error(
      JSON.stringify({
        level: "warn",
        component: "stress-intent-flows",
        message: "retrying_failed_intents",
        retryPass,
        count: retryable.length,
        treasury: app.treasuryEngine.report(),
      }),
    );
    for (const failed of retryable) {
      const retry = await retryIntent(app, valuation, failed, retryPass);
      if (retry) submitted.push(retry);
      await app.bus.drain();
    }
    await monitorUntilTerminal(app, submitted, Number(process.env.INTENT_STRESS_RETRY_TIMEOUT_MS ?? 300_000));
    results = [];
    for (const item of submitted) {
      const report = await app.reconciliationEngine.reconcile(item.intentId);
      await app.bus.drain();
      const events = app.store.events.byTransaction(item.intentId);
      results.push({
        ...item,
        eventTypes: events.map((event) => event.type),
        status: statusFor(events),
        integrity: report.integrity,
        errors: report.errors,
      });
    }
  }

  const allConfirmed = results.every(
    (result) =>
      result.status === "settlement.confirmed" &&
      result.integrity &&
      result.eventTypes.includes("execution.intent_created") &&
      result.eventTypes.includes("execution.scheduled") &&
      result.eventTypes.includes("execution.completed") &&
      result.eventTypes.includes("settlement.pending_confirmation") &&
      result.eventTypes.includes("settlement.confirmed"),
  );
  console.log(
    JSON.stringify(
      {
        mode: "intent-based-cow-uniswapx-style-stress",
        totalIntents: results.length,
        confirmed: results.filter((result) => result.status === "settlement.confirmed").length,
        failed: results.filter((result) => result.status.endsWith(".failed")).length,
        pending: results.filter((result) => result.status === "pending").length,
        allConfirmed,
        treasury: app.treasuryEngine.report(),
        results,
      },
      null,
      2,
    ),
  );
  if (!allConfirmed) process.exitCode = 1;
}

async function monitorUntilTerminal(
  app: ReturnType<typeof createTier1ExchangeApp>,
  submitted: Array<{ intentId: string }>,
  timeoutMs: number,
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await app.bus.drain();
    if (submitted.every((item) => terminal(app.store.events.byTransaction(item.intentId)))) return;
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }
}

async function retryIntent(
  app: ReturnType<typeof createTier1ExchangeApp>,
  valuation: ValuationService,
  failed: IntentStressResult,
  retryPass: number,
): Promise<{ intentId: string; type: "swap" | "offramp"; amount: string; target: string; route: string[]; twap: boolean; retryOf: string } | undefined> {
  if (failed.type === "swap") {
    let swapValuation;
    try {
      swapValuation = await valuation.swapNenoToAsset(failed.amount, failed.target);
    } catch {
      return undefined;
    }
    const intent = await app.intentService.createSwapIntent({
      idempotencyKey: `intent-stress-retry-swap-${Date.now()}-${retryPass}-${failed.intentId}`,
      accountId: process.env.STRESS_TEST_USER_ID ?? "massi-prod-001",
      fromAsset: "NENO",
      toAsset: failed.target,
      amount: failed.amount,
      expectedToAmount: swapValuation.targetAmount,
      provider: "real",
      metadata: {
        valuation: swapValuation,
        retryOf: failed.intentId,
        retryPass,
        slippageBps: Number(process.env.RETRY_SWAP_SLIPPAGE_BPS ?? process.env.SWAP_SLIPPAGE_BPS ?? 150),
        routePolicy: "retry-reroute-low-liquidity-paths",
      },
    });
    return { intentId: intent.intentId, type: "swap", amount: failed.amount, target: failed.target, route: intent.route, twap: intent.twap, retryOf: failed.intentId };
  }
  const rate = process.env.NENO_USDT_RATE ?? "20000";
  const offrampValuation = valuation.offrampNenoToFiatEquivalent(failed.amount, rate, "EUR");
  const intent = await app.intentService.createOfframpIntent({
    idempotencyKey: `intent-stress-retry-offramp-${Date.now()}-${retryPass}-${failed.intentId}`,
    accountId: process.env.STRESS_TEST_USER_ID ?? "massi-prod-001",
    fromAsset: "NENO",
    fiatCurrency: "EUR",
    amount: failed.amount,
    expectedFiatAmount: offrampValuation.targetAmount,
    provider: "real",
    metadata: {
      rate,
      valuation: offrampValuation,
      retryOf: failed.intentId,
      retryPass,
      routePolicy: "retry-with-treasury-rebalance-plan",
    },
  });
  return { intentId: intent.intentId, type: "offramp", amount: failed.amount, target: "EUR", route: intent.route, twap: intent.twap, retryOf: failed.intentId };
}

function terminal(events: Array<{ type: string }>): boolean {
  return events.some((event) => event.type === "settlement.confirmed" || event.type === "settlement.failed" || event.type === "execution.failed");
}

function statusFor(events: Array<{ type: string }>): IntentStressResult["status"] {
  if (events.some((event) => event.type === "settlement.confirmed")) return "settlement.confirmed";
  if (events.some((event) => event.type === "settlement.failed")) return "settlement.failed";
  if (events.some((event) => event.type === "execution.failed")) return "execution.failed";
  return "pending";
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
  const readiness = await new ExecutionReadinessController(app.assetRegistry).evaluate({ largeIntent: true });
  if (!readiness.allowed) {
    throw new Error(`Production execution readiness failed: ${JSON.stringify(readiness)}`);
  }
  if (!readiness.onChainBroadcastAllowed) {
    console.error(
      JSON.stringify({
        level: "warn",
        component: "stress-intent-flows",
        message: "treasury_not_funded_for_direct_broadcast_degraded_routing_enabled",
        treasury,
        readiness,
      }),
    );
  }
  const configuredMakers = new RFQAggregator().configuredProviders();
  if (configuredMakers.length === 0) {
    throw new Error("Production execution RFQ failed: no institutional maker or OTC endpoint configured for large ladder routing");
  }
}

main().catch((error) => {
  console.error(
    JSON.stringify({
      level: "error",
      component: "stress-intent-flows",
      error: error instanceof Error ? error.message : String(error),
    }),
  );
  process.exitCode = 1;
});
