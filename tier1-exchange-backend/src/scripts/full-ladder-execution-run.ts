import "../core/env.js";
process.env.SUPPRESS_EVENT_STREAM_LOGS ??= "1";

import { createTier1ExchangeApp } from "../app.js";
import { ExecutionReadinessController } from "../services/executionReadinessController.js";
import { BankPayoutRail } from "../services/bankPayoutRail.js";
import { DirectSepaPayoutRail } from "../services/directSepaPayoutRail.js";
import { ModulrPayoutRail } from "../services/modulrPayoutRail.js";
import { TreasuryOnChainService } from "../services/treasuryOnChainService.js";
import { ValuationService } from "../services/valuationService.js";
import type { ExecutionPlan } from "../services/executionPlanner.js";
import type { VenueQuote } from "../services/venueAdapter.js";

const SWAP_AMOUNTS = ["50", "100", "500", "1000", "5000", "10000", "20000", "50000", "100000", "200000"];
const SWAP_OUTPUTS = ["USDT", "USDC", "WBNB", "ETH", "BTC"] as const;
const OFFRAMP_AMOUNTS = ["100", "1000", "5000", "20000"];

type FlowType = "swap" | "offramp";
type FlowStatus =
  | "pre_execution_rejected"
  | "planning_failed"
  | "submitted"
  | "execution_failed"
  | "settlement_failed"
  | "settlement_pending"
  | "settlement_confirmed";

interface LadderResult {
  type: FlowType;
  amount: string;
  target: string;
  policy: string;
  status: FlowStatus;
  intentId?: string;
  route?: string[];
  twap?: boolean;
  selectedVenue?: string;
  selectedSource?: string;
  confidence?: number;
  referenceImpactBps?: number;
  reason?: string;
  txHash?: string;
  settlementId?: string;
  integrity?: boolean;
  eventTypes?: string[];
  errors?: string[];
  bankPayout?: Record<string, unknown>;
}

async function main(): Promise<void> {
  const app = createTier1ExchangeApp();
  await app.store.ready();
  const valuation = new ValuationService();
  const readiness = await new ExecutionReadinessController(app.assetRegistry).evaluate({ largeIntent: true });
  if (!readiness.allowed || !readiness.onChainBroadcastAllowed) {
    throw new Error(`Full ladder execution blocked by readiness gate: ${JSON.stringify(readiness)}`);
  }

  const results: LadderResult[] = [];
  for (const amount of SWAP_AMOUNTS) {
    for (const target of SWAP_OUTPUTS) {
      const result = await executeSwap(app, valuation, amount, target);
      results.push(result);
      await app.bus.drain();
      await monitorIfSubmitted(app, result);
      await finalizeResult(app, result);
    }
  }

  for (const amount of OFFRAMP_AMOUNTS) {
    const result = await executeOfframp(app, valuation, amount);
    results.push(result);
    await app.bus.drain();
    await monitorIfSubmitted(app, result);
    await finalizeResult(app, result);
  }

  const summary = {
    mode: "full-ladder-real-execution-run",
    pricingReference: "1 NENO = 20000 USDT",
    guardrails: {
      noFakeSettlement: true,
      noSyntheticTxHash: true,
      noForcedFinality: true,
      noMockLiquidity: true,
      preExecutionSimulationGate: true,
      bankPayoutFinalityGate: true,
      referenceImpactMode: process.env.REFERENCE_PRICE_GUARD_MODE ?? "advisory",
      referenceImpactAdvisoryBps: Number(process.env.MAX_REFERENCE_PRICE_IMPACT_BPS ?? 9500),
      minSuccessProbability: Number(process.env.PRE_EXECUTION_SUCCESS_THRESHOLD ?? 0.65),
    },
    readiness,
    treasury: await new TreasuryOnChainService(app.assetRegistry).balances(),
    totals: {
      flows: results.length,
      submitted: results.filter((result) => result.intentId).length,
      confirmed: results.filter((result) => result.status === "settlement_confirmed" && result.integrity).length,
      pending: results.filter((result) => result.status === "settlement_pending").length,
      failed: results.filter((result) => result.status === "execution_failed" || result.status === "settlement_failed").length,
      preExecutionRejected: results.filter((result) => result.status === "pre_execution_rejected" || result.status === "planning_failed").length,
    },
    breakdown: breakdown(results),
    results,
  };
  console.log(JSON.stringify(summary, null, 2));
  if (summary.totals.pending > 0) process.exitCode = 1;
}

async function executeSwap(
  app: ReturnType<typeof createTier1ExchangeApp>,
  valuation: ValuationService,
  amount: string,
  target: (typeof SWAP_OUTPUTS)[number],
): Promise<LadderResult> {
  try {
    const swapValuation = await valuation.swapNenoToAsset(amount, target);
    const plan = await app.executionPlanner.planSwap({
      accountId: process.env.STRESS_TEST_USER_ID ?? "massi-prod-001",
      fromAsset: "NENO",
      toAsset: target,
      amount,
      expectedToAmount: swapValuation.targetAmount,
    });
    const gate = executionGate(plan);
    const base = {
      type: "swap" as const,
      amount,
      target,
      policy: policyFor(amount),
      route: plan.route,
      twap: plan.twap,
      selectedVenue: gate.quote?.venue,
      selectedSource: gate.quote?.liquiditySource,
      confidence: gate.confidence,
      referenceImpactBps: gate.referenceImpactBps,
    };
    if (!gate.allowed) {
      return {
        ...base,
        status: "pre_execution_rejected",
        reason: gate.reason,
      };
    }
    const intent = await app.intentService.createSwapIntent({
      idempotencyKey: `full-ladder-swap-${Date.now()}-${amount}-${target}`,
      accountId: process.env.STRESS_TEST_USER_ID ?? "massi-prod-001",
      fromAsset: "NENO",
      toAsset: target,
      amount,
      expectedToAmount: swapValuation.targetAmount,
      provider: "real",
      metadata: {
        valuation: swapValuation,
        fullLadderExecutionRun: true,
        routeQuality: {
          confidence: gate.confidence,
          referenceImpactBps: gate.referenceImpactBps,
          selectedSource: gate.quote?.liquiditySource,
        },
      },
    });
    return {
      ...base,
      status: "submitted",
      intentId: intent.intentId,
      route: intent.route,
      twap: intent.twap,
    };
  } catch (error) {
    return {
      type: "swap",
      amount,
      target,
      policy: policyFor(amount),
      status: "planning_failed",
      reason: error instanceof Error ? error.message : String(error),
    };
  }
}

async function executeOfframp(app: ReturnType<typeof createTier1ExchangeApp>, valuation: ValuationService, amount: string): Promise<LadderResult> {
  try {
    const rate = process.env.NENO_USDT_RATE ?? "20000";
    const offrampValuation = valuation.offrampNenoToFiatEquivalent(amount, rate, "EUR");
    const plan = app.executionPlanner.planOfframp({ fromAsset: "NENO", fiatCurrency: "EUR", amount });
    const bankPayout = await payoutReadinessForEnv(offrampValuation.targetAmount);
    if (!bankPayout.ready) {
      return {
        type: "offramp",
        amount,
        target: "EUR",
        policy: Number(amount) <= 1000 ? "treasury-direct" : "clearing-netting-rfq",
        status: "pre_execution_rejected",
        route: plan.route,
        twap: plan.twap,
        reason: `BANK_PAYOUT_RAIL_NOT_READY:${bankPayout.reason ?? "unknown"}`,
        bankPayout: bankPayout as unknown as Record<string, unknown>,
      };
    }
    if (process.env.FULL_LADDER_OFFRAMP_SUBMIT === "0") {
      return {
        type: "offramp",
        amount,
        target: "EUR",
        policy: Number(amount) <= 1000 ? "treasury-direct" : "clearing-netting-rfq",
        status: "pre_execution_rejected",
        route: plan.route,
        twap: plan.twap,
        reason: "FULL_LADDER_OFFRAMP_SUBMIT=0",
        bankPayout: bankPayout as unknown as Record<string, unknown>,
      };
    }
    const intent = await app.intentService.createOfframpIntent({
      idempotencyKey: `full-ladder-offramp-${Date.now()}-${amount}`,
      accountId: process.env.STRESS_TEST_USER_ID ?? "massi-prod-001",
      fromAsset: "NENO",
      fiatCurrency: "EUR",
      amount,
      expectedFiatAmount: offrampValuation.targetAmount,
      provider: "real",
      metadata: {
        rate,
        valuation: offrampValuation,
        fullLadderExecutionRun: true,
        bankPayout: {
          destination: bankPayout.destination,
          provider: bankPayout.provider,
          readinessProof: bankPayout.proof,
          payoutPolicy: "execute-only-after-settlement-confirmed-and-reconciliation-valid",
        },
      },
    });
    return {
      type: "offramp",
      amount,
      target: "EUR",
      policy: Number(amount) <= 1000 ? "treasury-direct" : "clearing-netting-rfq",
      status: "submitted",
      intentId: intent.intentId,
      route: intent.route,
      twap: intent.twap,
      bankPayout: bankPayout as unknown as Record<string, unknown>,
    };
  } catch (error) {
    return {
      type: "offramp",
      amount,
      target: "EUR",
      policy: Number(amount) <= 1000 ? "treasury-direct" : "clearing-netting-rfq",
      status: "planning_failed",
      reason: error instanceof Error ? error.message : String(error),
    };
  }
}

function executionGate(plan: ExecutionPlan): { allowed: boolean; reason?: string; quote?: VenueQuote; confidence?: number; referenceImpactBps?: number } {
  const quote = plan.sor?.selected?.quote;
  if (!quote) return { allowed: false, reason: "NO_EXECUTABLE_SOR_ROUTE" };
  const confidence = Number(quote.metadata.executionSuccessProbability ?? 0);
  const referenceImpactBps = Number(quote.metadata.referenceSlippageBps ?? 0);
  const minConfidence = Number(process.env.PRE_EXECUTION_SUCCESS_THRESHOLD ?? 0.65);
  const maxReferenceImpactBps = Number(process.env.MAX_REFERENCE_PRICE_IMPACT_BPS ?? 9500);
  const referenceGuardMode = String(process.env.REFERENCE_PRICE_GUARD_MODE ?? "advisory").toLowerCase();
  if (!quote.metadata.executable) return { allowed: false, quote, confidence, referenceImpactBps, reason: "NO_EXECUTABLE_CALLDATA" };
  if (!Number.isFinite(confidence) || confidence < minConfidence) {
    return { allowed: false, quote, confidence, referenceImpactBps, reason: `EXPECTED_SUCCESS_PROBABILITY_BELOW_THRESHOLD:${confidence}` };
  }
  if (referenceGuardMode === "hard" && Number.isFinite(referenceImpactBps) && referenceImpactBps > maxReferenceImpactBps) {
    return { allowed: false, quote, confidence, referenceImpactBps, reason: `REFERENCE_PRICE_IMPACT_EXCEEDED:${referenceImpactBps}bps` };
  }
  return { allowed: true, quote, confidence, referenceImpactBps };
}

async function monitorIfSubmitted(app: ReturnType<typeof createTier1ExchangeApp>, result: LadderResult): Promise<void> {
  if (!result.intentId) return;
  const deadline = Date.now() + Number(process.env.FULL_LADDER_FLOW_TIMEOUT_MS ?? 300_000);
  while (Date.now() < deadline) {
    await app.bus.drain();
    const events = app.store.events.byTransaction(result.intentId);
    if (events.some((event) => event.type === "settlement.confirmed" || event.type === "settlement.failed" || event.type === "execution.failed")) return;
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }
}

async function finalizeResult(app: ReturnType<typeof createTier1ExchangeApp>, result: LadderResult): Promise<void> {
  if (!result.intentId) return;
  const events = app.store.events.byTransaction(result.intentId);
  const report = await app.reconciliationEngine.reconcile(result.intentId);
  await app.bus.drain();
  const latestEvents = app.store.events.byTransaction(result.intentId);
  const initiated = latestEvents.find((event) => event.type === "settlement.initiated");
  result.eventTypes = latestEvents.map((event) => event.type);
  result.txHash = typeof initiated?.payload.txHash === "string" ? initiated.payload.txHash : undefined;
  result.settlementId = typeof initiated?.payload.settlementId === "string" ? initiated.payload.settlementId : undefined;
  result.integrity = report.integrity;
  result.errors = report.errors;
  if (latestEvents.some((event) => event.type === "settlement.confirmed")) result.status = "settlement_confirmed";
  else if (latestEvents.some((event) => event.type === "settlement.pending_confirmation")) result.status = "settlement_pending";
  else if (latestEvents.some((event) => event.type === "settlement.failed")) result.status = "settlement_failed";
  else if (latestEvents.some((event) => event.type === "execution.failed")) result.status = "execution_failed";
  else if (events.length > 0) result.status = "settlement_pending";
}

function breakdown(results: LadderResult[]): Record<string, unknown> {
  const byType = (type: FlowType) => results.filter((result) => result.type === type);
  return {
    swap: breakdownRows(byType("swap")),
    offramp: breakdownRows(byType("offramp")),
    routing: Object.fromEntries(
      [...new Set(results.map((result) => result.selectedSource ?? "none"))].map((source) => [
        source,
        results.filter((result) => (result.selectedSource ?? "none") === source).length,
      ]),
    ),
  };
}

function breakdownRows(results: LadderResult[]): Record<string, number> {
  return Object.fromEntries([...new Set(results.map((result) => result.status))].map((status) => [status, results.filter((result) => result.status === status).length]));
}

function policyFor(amount: string): string {
  const value = Number(amount);
  if (value <= 500) return "sor-rfq-direct";
  if (value <= 10_000) return "rfq-sor-adaptive-twap";
  if (value <= 100_000) return "rfq-dark-liquidity-internal-crossing";
  return "staged-otc-partial-fills-only";
}

async function payoutReadinessForEnv(amount: string): Promise<{
  ready: boolean;
  provider?: string;
  destination: ReturnType<BankPayoutRail["destination"]>;
  amount: string;
  currency: "EUR";
  reason?: string;
  proof?: Record<string, unknown>;
}> {
  const rail = String(process.env.PAYOUT_RAIL ?? process.env.BANK_RAIL_PROVIDER ?? "direct-sepa").toLowerCase();
  if (rail === "wise") return new BankPayoutRail().readiness(amount);
  if (rail === "modulr") return new ModulrPayoutRail().readiness(amount);
  return new DirectSepaPayoutRail().readiness(amount);
}

main().catch((error) => {
  console.error(
    JSON.stringify({
      level: "error",
      component: "full-ladder-execution-run",
      error: error instanceof Error ? error.message : String(error),
    }),
  );
  process.exitCode = 1;
});
