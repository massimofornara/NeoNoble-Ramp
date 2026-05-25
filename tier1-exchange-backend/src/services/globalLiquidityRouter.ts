import { LiquidityGraphOptimizer } from "./liquidityGraphOptimizer.js";
import { UniversalLiquidityAbstractionLayer } from "./universalLiquidityAbstractionLayer.js";
import type { InstitutionalRfqDecision } from "./institutionalRfqAggregator.js";
import type { RfqDecision } from "./rfqEngine.js";
import type { SmartRouteDecision } from "./sorEngine.js";

export class GlobalLiquidityRouter {
  constructor(
    private readonly universal = new UniversalLiquidityAbstractionLayer(),
    private readonly optimizer = new LiquidityGraphOptimizer(),
  ) {}

  route(input: { sor: SmartRouteDecision; rfq: RfqDecision; institutional: InstitutionalRfqDecision; darkLiquidity: Record<string, unknown>; internalCrossing: Record<string, unknown> }): Record<string, unknown> {
    const unified = this.universal.unify(input);
    return {
      unified,
      graph: this.optimizer.optimize([
        { name: "internal-crossing", available: true },
        { name: "sor-defi", available: input.sor.ranked.length > 0 },
        { name: "rfq-otc", available: input.rfq.quotes.length > 0 },
        { name: "institutional-makers", available: input.institutional.quotes.length > 0 },
        { name: "dark-liquidity", available: Boolean(input.darkLiquidity.enabled) },
      ]),
    };
  }
}
