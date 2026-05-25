import { LiquidityRouter, type LiquidityPath } from "./liquidityRouter.js";
import { AdaptiveTwapExecutor } from "./adaptiveTwapExecutor.js";
import { ClearingEngine, type ClearingPlan } from "./clearingEngine.js";
import { CrossChainRouter } from "./crossChainRouter.js";
import { DarkLiquidityRouter } from "./darkLiquidityRouter.js";
import { GlobalLiquidityRouter } from "./globalLiquidityRouter.js";
import { InstitutionalRfqAggregator, type InstitutionalRfqDecision } from "./institutionalRfqAggregator.js";
import { InternalCrossingEngine, type CrossingDecision } from "./internalCrossingEngine.js";
import { MevProtectionService } from "./mevProtectionService.js";
import { PortfolioEngine } from "./portfolioEngine.js";
import { PredictiveLiquidityRouting } from "./predictiveLiquidityRouting.js";
import { TreasuryOnChainService } from "./treasuryOnChainService.js";
import type { RfqDecision } from "./rfqEngine.js";
import { SorEngine, type SmartRouteDecision } from "./sorEngine.js";
import type { TwapSlice } from "./twapExecutor.js";

export interface SwapIntentPlanningInput {
  intentId?: string;
  accountId?: string;
  fromAsset: string;
  toAsset: string;
  amount: string;
}

export interface OfframpIntentPlanningInput {
  fromAsset: string;
  fiatCurrency: string;
  amount: string;
}

export interface ExecutionPlan {
  planId: string;
  executionStyle: "direct-amm" | "chunked-twap" | "full-twap" | "offramp-ladder";
  twap: boolean;
  route: string[];
  selectedPath?: LiquidityPath;
  candidatePaths?: LiquidityPath[];
  sor?: SmartRouteDecision;
  rfq?: RfqDecision;
  institutionalRfq?: InstitutionalRfqDecision;
  crossing?: CrossingDecision;
  clearing?: ClearingPlan;
  mevProtection?: Record<string, unknown>;
  crossChain?: Record<string, unknown>;
  portfolio?: Record<string, unknown>;
  treasury?: Record<string, unknown>;
  darkLiquidity?: Record<string, unknown>;
  globalLiquidity?: Record<string, unknown>;
  aiExecution?: Record<string, unknown>;
  slices: TwapSlice[];
  solverFallbacks: string[];
  batchSettlement: boolean;
  fiatRoute?: "EUR-SEPA";
}

export class ExecutionPlanner {
  constructor(
    private readonly liquidityRouter = new LiquidityRouter(),
    private readonly twapExecutor = new AdaptiveTwapExecutor(),
    private readonly sor = new SorEngine(),
    private readonly institutionalRfq = new InstitutionalRfqAggregator(),
    private readonly crossing = new InternalCrossingEngine(),
    private readonly clearing = new ClearingEngine(),
    private readonly mev = new MevProtectionService(),
    private readonly crossChain = new CrossChainRouter(),
    private readonly portfolio = new PortfolioEngine(),
    private readonly darkLiquidity = new DarkLiquidityRouter(),
    private readonly globalLiquidity = new GlobalLiquidityRouter(),
    private readonly predictiveRouting = new PredictiveLiquidityRouting(),
    private readonly treasury = new TreasuryOnChainService(),
  ) {}

  async planSwap(input: SwapIntentPlanningInput & { expectedToAmount?: string }): Promise<ExecutionPlan> {
    const profile = swapProfile(input.amount);
    const quoteRequest = {
      chainId: Number(process.env.BSC_CHAIN_ID ?? process.env.CHAIN_ID ?? 56),
      fromAsset: input.fromAsset,
      toAsset: input.toAsset,
      amount: input.amount,
      expectedToAmount: input.expectedToAmount,
      slippageBps: Number(process.env.SWAP_SLIPPAGE_BPS ?? 75),
    };
    const [sorDecision, rfqDecision, institutionalRfqDecision, treasuryContext] = await Promise.all([
      this.sor.discover(quoteRequest),
      Promise.resolve(emptyRfqDecision(input.amount)),
      this.institutionalRfq.aggregate(quoteRequest),
      this.treasury.balances().catch((error: unknown) => ({
        unavailable: true,
        reason: error instanceof Error ? error.message : String(error),
      })),
    ]);
    const crossingDecision = this.crossing.evaluate({
      intentId: input.intentId ?? `planning-${Date.now()}`,
      accountId: input.accountId ?? "unknown-account",
      fromAsset: input.fromAsset,
      toAsset: input.toAsset,
      amount: input.amount,
      expectedAmount: input.expectedToAmount ?? input.amount,
    });
    const clearingPlan = this.clearing.plan(input.intentId ?? `planning-${Date.now()}`, [
      { intentId: input.intentId ?? "planning", asset: input.fromAsset, amount: input.amount, direction: "in" },
      { intentId: input.intentId ?? "planning", asset: input.toAsset, amount: input.expectedToAmount ?? input.amount, direction: "out" },
    ]);
    const executableRfq = institutionalRfqDecision.selectedExecutable ?? rfqDecision.quotes.find((quote) => Boolean(quote.metadata.executable));
    const executableSor = sorDecision.ranked.map((route) => route.quote).find((quote) => Boolean(quote.metadata.executable));
    const selectedQuote = executableRfq ?? executableSor ?? institutionalRfqDecision.selected ?? rfqDecision.selected?.quote ?? sorDecision.selected?.quote;
    const paths = this.liquidityRouter.swapPaths(input.fromAsset, input.toAsset);
    const selected = this.liquidityRouter.bestSwapPath(input.fromAsset, input.toAsset);
    const quotes = [
      ...(sorDecision.ranked.map((route) => route.quote)),
      ...rfqDecision.quotes,
      ...institutionalRfqDecision.quotes,
    ];
    const darkLiquidity = this.darkLiquidity.route(input.toAsset, input.amount);
    const globalLiquidity = this.globalLiquidity.route({
      sor: sorDecision,
      rfq: rfqDecision,
      institutional: institutionalRfqDecision,
      darkLiquidity,
      internalCrossing: crossingDecision as unknown as Record<string, unknown>,
    });
    const aiExecution = this.predictiveRouting.optimize({
      asset: input.toAsset,
      amount: input.amount,
      quoteCount: sorDecision.ranked.length,
      rfqCount: rfqDecision.quotes.length + institutionalRfqDecision.quotes.length,
      privateSettlement: Boolean(selectedQuote?.privateSettlement),
    });
    const slices = this.twapExecutor.plan(input.amount, profile === "direct-amm" ? "direct" : profile === "chunked-twap" ? "medium" : "large", quotes);
    return {
      planId: `plan_${profile}_${Date.now()}`,
      executionStyle: profile,
      twap: profile !== "direct-amm",
      route: crossingDecision.matches.length > 0 ? ["internal-crossing", ...(selectedQuote?.route ?? selected.symbols)] : selectedQuote?.route ?? selected.symbols,
      selectedPath: selected,
      candidatePaths: paths,
      sor: sorDecision,
      rfq: rfqDecision,
      institutionalRfq: institutionalRfqDecision,
      crossing: crossingDecision,
      clearing: clearingPlan,
      mevProtection: this.mev.protect({ chainId: quoteRequest.chainId, metadata: { fromAsset: input.fromAsset, toAsset: input.toAsset, amount: input.amount } }),
      crossChain: this.crossChain.plan(input.toAsset),
      portfolio: this.portfolio.assess(input.toAsset, input.expectedToAmount ?? input.amount, input.expectedToAmount ?? input.amount),
      treasury: treasuryRoutingContext(treasuryContext, input.toAsset),
      darkLiquidity,
      globalLiquidity,
      aiExecution,
      slices: slices.map((slice, index) => ({
        ...slice,
        slippageBps: profile === "full-twap" ? Math.max(slice.slippageBps, 100) : slice.slippageBps,
        sequence: index + 1,
      })),
      solverFallbacks: rfqDecision.required
        ? ["institutional-rfq", "dark-liquidity", "rfq-private-settlement", "otc-maker-retry"]
        : ["internal-crossing", "institutional-rfq-executable", "global-liquidity-router", "smart-order-router", "rfq-optional", "adaptive-twap", "private-relay", "fallback-amm-router"],
      batchSettlement: profile !== "direct-amm",
    };
  }

  planOfframp(input: OfframpIntentPlanningInput): ExecutionPlan {
    const slices = this.twapExecutor.plan(input.amount, "offramp", []);
    const clearingPlan = this.clearing.plan(`offramp-${Date.now()}`, [
      { intentId: "offramp", asset: input.fromAsset, amount: input.amount, direction: "in" },
      { intentId: "offramp", asset: input.fiatCurrency, amount: input.amount, direction: "out" },
    ]);
    return {
      planId: `plan_offramp_${Date.now()}`,
      executionStyle: "offramp-ladder",
      twap: slices.length > 1,
      route: [input.fromAsset.toUpperCase(), input.fiatCurrency.toUpperCase()],
      slices,
      clearing: clearingPlan,
      crossChain: this.crossChain.plan(input.fromAsset),
      portfolio: this.portfolio.assess(input.fiatCurrency, input.amount, input.amount),
      solverFallbacks: ["internal-netting", "provider-routing", "treasury-retry", "cross-chain-rebalance", "twap-fallback"],
      batchSettlement: slices.length > 1,
      fiatRoute: "EUR-SEPA",
    };
  }
}

function swapProfile(amount: string): "direct-amm" | "chunked-twap" | "full-twap" {
  const value = Number(amount);
  if (!Number.isFinite(value) || value <= 0) throw new Error(`Invalid swap amount: ${amount}`);
  if (value < 500) return "direct-amm";
  if (value <= 10_000) return "chunked-twap";
  return "full-twap";
}

function emptyRfqDecision(amount: string): RfqDecision {
  return {
    required: Number(amount) > 100_000,
    preferred: Number(amount) > 20_000,
    quotes: [],
  };
}

function treasuryRoutingContext(treasury: Record<string, unknown>, toAsset: string): Record<string, unknown> {
  const balances = Array.isArray(treasury.balances) ? (treasury.balances as Array<Record<string, unknown>>) : [];
  const target = toAsset.toUpperCase();
  const wrappedTarget = target === "ETH" ? "WETH" : target === "BTC" ? "WBTC" : target;
  const row = balances.find((item) => String(item.asset).toUpperCase() === wrappedTarget || String(item.asset).toUpperCase() === target);
  const nativeGas = Array.isArray(treasury.nativeGas) ? (treasury.nativeGas as Array<Record<string, unknown>>) : [];
  return {
    outputAsset: target,
    inventoryAvailable: String(row?.balance ?? "0"),
    inventoryPositive: Number(row?.balance ?? 0) > 0,
    gasReserveHealthy: nativeGas.every((item) => item.sufficient !== false),
    treasuryFundedForSource: Boolean((treasury as { fundingSufficientForConfiguredBatch?: boolean }).fundingSufficientForConfiguredBatch),
    exposurePolicy: "prefer-internal-inventory-before-external-liquidity-when-positive",
  };
}
