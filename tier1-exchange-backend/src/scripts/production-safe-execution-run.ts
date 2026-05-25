import "../core/env.js";
process.env.SUPPRESS_EVENT_STREAM_LOGS ??= "1";
import { createTier1ExchangeApp } from "../app.js";
import { ExecutionReadinessController } from "../services/executionReadinessController.js";
import { RFQAggregator } from "../services/rfqAggregator.js";
import { TreasuryFundingBootstrapService } from "../services/treasuryFundingBootstrapService.js";
import { TreasuryOnChainService } from "../services/treasuryOnChainService.js";
import { ValuationService } from "../services/valuationService.js";

const SWAP_AMOUNTS = ["50", "500", "1000", "5000", "10000", "100000"];
const SWAP_OUTPUTS = ["USDT", "USDC", "WBNB", "ETH", "BTC"] as const;
const OFFRAMP_AMOUNTS = ["100", "1000", "5000", "20000"];

interface PlannedFlow {
  type: "swap" | "offramp";
  amount: string;
  target: string;
  policy: string;
  status: "planned" | "submitted" | "planning_failed" | "execution_failed" | "settlement_confirmed" | "settlement_pending";
  intentId?: string;
  route?: string[];
  twap?: boolean;
  reason?: string;
  integrity?: boolean;
}

async function main(): Promise<void> {
  const app = createTier1ExchangeApp();
  await app.store.ready();
  const valuation = new ValuationService();
  const readiness = await new ExecutionReadinessController(app.assetRegistry).evaluate({ largeIntent: true });
  const treasury = await new TreasuryOnChainService(app.assetRegistry).balances();
  const bootstrap = await new TreasuryFundingBootstrapService(app.assetRegistry).plan();
  const rfqGateway = new RFQAggregator();
  const providerStatuses = rfqGateway.statuses();
  const productionMakers = providerStatuses.filter((provider) => provider.configured);
  const submitIntents =
    readiness.onChainBroadcastAllowed || (readiness.degradedExecutionAllowed && process.env.PRODUCTION_SAFE_SUBMIT_DEGRADED_INTENTS === "1");
  const flows: PlannedFlow[] = [];

  for (const amount of SWAP_AMOUNTS) {
    for (const target of SWAP_OUTPUTS) {
      flows.push(await planSwap(app, valuation, amount, target, submitIntents));
    }
  }
  for (const amount of OFFRAMP_AMOUNTS) {
    flows.push(await planOfframp(app, valuation, amount, submitIntents));
  }

  if (flows.some((flow) => flow.intentId)) {
    await app.bus.drain();
    await monitor(app, flows);
    for (const flow of flows.filter((item) => item.intentId)) {
      const report = await app.reconciliationEngine.reconcile(String(flow.intentId));
      const events = app.store.events.byTransaction(String(flow.intentId));
      flow.integrity = report.integrity;
      if (events.some((event) => event.type === "settlement.confirmed")) flow.status = "settlement_confirmed";
      else if (events.some((event) => event.type === "settlement.pending_confirmation")) flow.status = "settlement_pending";
      else if (events.some((event) => event.type === "execution.failed" || event.type === "settlement.failed")) flow.status = "execution_failed";
    }
  }

  const confirmed = flows.filter((flow) => flow.status === "settlement_confirmed" && flow.integrity).length;
  const report = {
    mode: "production-safe-execution-run",
    safeguards: {
      intentBasedExecution: true,
      adaptiveRouting: true,
      rfqPriorityForMediumAndLargeSize: true,
      internalCrossing: true,
      darkLiquidityRouting: true,
      mevProtection: true,
      settlementFinality: "chain-or-provider-proof-required",
    },
    readiness,
    treasury,
    bootstrap,
    rfq: {
      active: productionMakers.length > 0,
      configuredMakers: productionMakers.map((provider) => provider.provider),
      providerStatuses,
      schemaValidSimulatorActive: false,
      fallbackOrder: ["rfq-retry", "sor-reroute", "twap-split", "internal-crossing", "amm-last-resort"],
    },
    submitIntents,
    submitted: flows.filter((flow) => flow.intentId).length,
    confirmed,
    pending: flows.filter((flow) => flow.status === "settlement_pending").length,
    failed: flows.filter((flow) => flow.status === "execution_failed" || flow.status === "planning_failed").length,
    plannedOnly: flows.filter((flow) => flow.status === "planned").length,
    flows,
  };
  console.log(JSON.stringify(report, null, 2));
  if (!readiness.allowed) process.exitCode = 1;
}

async function planSwap(
  app: ReturnType<typeof createTier1ExchangeApp>,
  valuation: ValuationService,
  amount: string,
  target: (typeof SWAP_OUTPUTS)[number],
  submitIntents: boolean,
): Promise<PlannedFlow> {
  try {
    const swapValuation = await valuation.swapNenoToAsset(amount, target);
    const plan = await app.executionPlanner.planSwap({
      accountId: process.env.STRESS_TEST_USER_ID ?? "massi-prod-001",
      fromAsset: "NENO",
      toAsset: target,
      amount,
      expectedToAmount: swapValuation.targetAmount,
    });
    if (!submitIntents) {
      return { type: "swap", amount, target, policy: policyFor(amount), status: "planned", route: plan.route, twap: plan.twap };
    }
    const intent = await app.intentService.createSwapIntent({
      idempotencyKey: `production-safe-swap-${Date.now()}-${amount}-${target}`,
      accountId: process.env.STRESS_TEST_USER_ID ?? "massi-prod-001",
      fromAsset: "NENO",
      toAsset: target,
      amount,
      expectedToAmount: swapValuation.targetAmount,
      provider: "real",
      metadata: {
        valuation: swapValuation,
        productionSafeRun: true,
      },
    });
    return { type: "swap", amount, target, policy: policyFor(amount), status: "submitted", intentId: intent.intentId, route: intent.route, twap: intent.twap };
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

async function planOfframp(
  app: ReturnType<typeof createTier1ExchangeApp>,
  valuation: ValuationService,
  amount: string,
  submitIntents: boolean,
): Promise<PlannedFlow> {
  try {
    const rate = process.env.NENO_USDT_RATE ?? "20000";
    const offrampValuation = valuation.offrampNenoToFiatEquivalent(amount, rate, "EUR");
    const plan = app.executionPlanner.planOfframp({ fromAsset: "NENO", fiatCurrency: "EUR", amount });
    if (!submitIntents) {
      return { type: "offramp", amount, target: "EUR", policy: Number(amount) <= 1000 ? "treasury-direct" : "clearing-netting-rfq", status: "planned", route: plan.route, twap: plan.twap };
    }
    const intent = await app.intentService.createOfframpIntent({
      idempotencyKey: `production-safe-offramp-${Date.now()}-${amount}`,
      accountId: process.env.STRESS_TEST_USER_ID ?? "massi-prod-001",
      fromAsset: "NENO",
      fiatCurrency: "EUR",
      amount,
      expectedFiatAmount: offrampValuation.targetAmount,
      provider: "real",
      metadata: {
        rate,
        valuation: offrampValuation,
        productionSafeRun: true,
      },
    });
    return { type: "offramp", amount, target: "EUR", policy: Number(amount) <= 1000 ? "treasury-direct" : "clearing-netting-rfq", status: "submitted", intentId: intent.intentId, route: intent.route, twap: intent.twap };
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

async function monitor(app: ReturnType<typeof createTier1ExchangeApp>, flows: PlannedFlow[]): Promise<void> {
  const deadline = Date.now() + Number(process.env.PRODUCTION_SAFE_RUN_TIMEOUT_MS ?? 300_000);
  while (Date.now() < deadline) {
    await app.bus.drain();
    const submitted = flows.filter((flow) => flow.intentId);
    if (submitted.every((flow) => terminal(app.store.events.byTransaction(String(flow.intentId))))) return;
    await new Promise((resolve) => setTimeout(resolve, 2_000));
  }
}

function terminal(events: Array<{ type: string }>): boolean {
  return events.some((event) => event.type === "settlement.confirmed" || event.type === "settlement.failed" || event.type === "execution.failed");
}

function policyFor(amount: string): string {
  const value = Number(amount);
  if (value < 500) return "amm-sor";
  if (value <= 10_000) return "twap-rfq";
  return "rfq-internal-crossing-dark-liquidity";
}

main().catch((error) => {
  console.error(
    JSON.stringify({
      level: "error",
      component: "production-safe-execution-run",
      error: error instanceof Error ? error.message : String(error),
    }),
  );
  process.exitCode = 1;
});
