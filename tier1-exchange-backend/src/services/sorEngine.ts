import { QuoteAggregator, type AggregatedQuotes } from "./quoteAggregator.js";
import { RouteScorer, type ScoredRoute } from "./routeScorer.js";
import { ExternalVenueAdapter, V2AmmVenueAdapter, type ExecutionVenueAdapter, type QuoteRequest } from "./venueAdapter.js";
import { OneInchFusionAdapter } from "./oneInchFusionAdapter.js";
import { ZeroExSwapAdapter } from "./zeroExSwapAdapter.js";
import { DwfLiquidMarketsAdapter } from "./dwfLiquidMarketsAdapter.js";
import { PreExecutionSimulationGate } from "./preExecutionSimulationGate.js";
import { logJson, metrics } from "../core/observability.js";

export interface SmartRouteDecision {
  selected?: ScoredRoute;
  ranked: ScoredRoute[];
  aggregate: AggregatedQuotes;
  policy: {
    objective: "maximize_gas_adjusted_execution_quality";
    minFailureProbability: number;
    maxSlippageBps: number;
  };
}

export class SorEngine {
  private readonly aggregator: QuoteAggregator;
  private readonly scorer = new RouteScorer();
  private readonly simulationGate = new PreExecutionSimulationGate();

  constructor(adapters = defaultAdapters()) {
    this.aggregator = new QuoteAggregator(adapters);
  }

  async discover(request: QuoteRequest): Promise<SmartRouteDecision> {
    const aggregate = await this.aggregator.aggregate(request);
    const gate = await this.simulationGate.validateQuotes(aggregate.quotes, request);
    const gatedAggregate = {
      ...aggregate,
      quotes: gate.validQuotes,
      unavailableVenues: [
        ...aggregate.unavailableVenues,
        ...gate.rejected.map(({ quote, result }) => ({
          venue: quote.venue,
          reason: `pre_execution_rejected:${result.normalizedFailureReason ?? "LOW_CONFIDENCE"}:${result.rejectionReason ?? "confidence below threshold"}`,
        })),
      ],
    };
    const maxSlippageBps = Number(process.env.SOR_MAX_SLIPPAGE_BPS ?? 5000);
    const maxFailureProbability = Number(process.env.SOR_MAX_FAILURE_PROBABILITY ?? 0.35);
    const ranked = this.scorer
      .score(gatedAggregate.quotes)
      .filter((route) => route.quote.slippageBps <= maxSlippageBps && route.quote.failureProbability <= maxFailureProbability);
    const selected = ranked[0];
    logJson("sor-engine", "route_decision", {
      transactionId: request.intentId,
      fromAsset: request.fromAsset,
      toAsset: request.toAsset,
      amount: request.amount,
      selectedVenue: selected?.quote.venue,
      selectedSource: selected?.quote.liquiditySource,
      confidence: selected?.quote.metadata.executionSuccessProbability,
      selectionReason: selectionReason(selected),
      quoteCount: ranked.length,
      rejectedCount: gate.rejected.length,
    });
    if (selected) {
      metrics.inc("exchange_route_decisions_total", {
        venue: selected.quote.venue,
        source: selected.quote.liquiditySource,
        executable: Boolean(selected.quote.metadata.executable),
      });
    }
    return {
      selected,
      ranked,
      aggregate: gatedAggregate,
      policy: {
        objective: "maximize_gas_adjusted_execution_quality",
        minFailureProbability: maxFailureProbability,
        maxSlippageBps,
      },
    };
  }
}

function defaultAdapters(): ExecutionVenueAdapter[] {
  return [
    new ZeroExSwapAdapter(),
    new OneInchFusionAdapter(),
    new DwfLiquidMarketsAdapter(),
    new V2AmmVenueAdapter("pancakeswap", "BSC_SWAP_ROUTER_ADDRESS", "BSC_RPC_URL", "pancake-v2"),
    new V2AmmVenueAdapter("uniswap", "UNISWAP_V2_ROUTER_ADDRESS", "ETHEREUM_RPC_URL", "uniswap-v2"),
    new ExternalVenueAdapter("openocean", "OPENOCEAN_QUOTE_URL", "OPENOCEAN_API_KEY"),
    new ExternalVenueAdapter("kyberswap", "KYBERSWAP_QUOTE_URL", "KYBERSWAP_API_KEY"),
    new ExternalVenueAdapter("cow", "COW_SOLVER_QUOTE_URL", "COW_SOLVER_API_KEY"),
  ];
}

function selectionReason(selected: ScoredRoute | undefined): string {
  if (!selected) return "no_route_after_pre_execution_gate";
  if (selected.quote.liquiditySource === "0x_RFQ") return "rfq_embedded_executable_quote";
  if (selected.quote.liquiditySource === "1inch_fusion") return "intent_solver_mev_resistant_quote";
  if (selected.quote.metadata.executable) return "executable_calldata_best_score";
  return "quote_only_best_score";
}
