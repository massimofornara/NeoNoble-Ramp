import type { ExecutionPlan } from "./executionPlanner.js";

export class RoutingIntelligence {
  explain(plan: ExecutionPlan): Record<string, unknown> {
    return {
      planId: plan.planId,
      route: plan.route,
      twap: plan.twap,
      solverFallbacks: plan.solverFallbacks,
      selectedVenue: plan.rfq?.selected?.quote.liquiditySource ?? plan.sor?.selected?.quote.liquiditySource ?? "internal-routing",
      institutionalVenue: plan.institutionalRfq?.selected?.liquiditySource ?? "none",
      crossingApplied: Number(plan.crossing?.matches.length ?? 0) > 0,
      darkLiquidityEnabled: Boolean(plan.darkLiquidity?.enabled),
      globalLiquidity: plan.globalLiquidity,
      aiExecution: plan.aiExecution,
    };
  }
}
