import type { InstitutionalRfqDecision } from "./institutionalRfqAggregator.js";
import type { RfqDecision } from "./rfqEngine.js";
import type { SmartRouteDecision } from "./sorEngine.js";

export class UniversalLiquidityAbstractionLayer {
  unify(input: { sor: SmartRouteDecision; rfq: RfqDecision; institutional: InstitutionalRfqDecision; darkLiquidity: Record<string, unknown>; internalCrossing: Record<string, unknown> }): Record<string, unknown> {
    return {
      ceFi: input.institutional.quotes.length,
      deFi: input.sor.ranked.length,
      otc: input.rfq.quotes.length,
      darkPools: Array.isArray(input.darkLiquidity.eligibleProviders) ? input.darkLiquidity.eligibleProviders.length : 0,
      internalInventory: input.internalCrossing,
      bestSource:
        input.institutional.selected?.liquiditySource ??
        input.rfq.selected?.quote.liquiditySource ??
        input.sor.selected?.quote.liquiditySource ??
        "none_available",
    };
  }
}
