import { AdaptiveExecutionModel } from "./adaptiveExecutionModel.js";
import { ExecutionSimulationEngine } from "./executionSimulationEngine.js";
import { ProbabilisticSettlementScoring } from "./probabilisticSettlementScoring.js";
import { VolatilityForecastingEngine } from "./volatilityForecastingEngine.js";

export class PredictiveLiquidityRouting {
  constructor(
    private readonly volatility = new VolatilityForecastingEngine(),
    private readonly scoring = new ProbabilisticSettlementScoring(),
    private readonly simulation = new ExecutionSimulationEngine(),
    private readonly model = new AdaptiveExecutionModel(),
  ) {}

  optimize(input: { asset: string; amount: string; quoteCount: number; rfqCount: number; privateSettlement: boolean }): Record<string, unknown> {
    const forecast = this.volatility.forecast(input.asset);
    const settlement = this.scoring.score({
      quoteCount: input.quoteCount,
      rfqCount: input.rfqCount,
      privateSettlement: input.privateSettlement,
      volatilityBps: Number(forecast.volatilityBps),
    });
    return {
      forecast,
      settlement,
      simulation: this.simulation.simulate({
        amount: input.amount,
        routeCount: input.quoteCount + input.rfqCount,
        settlementProbability: Number(settlement.probability),
      }),
      model: this.model.choose({
        amount: input.amount,
        settlementProbability: Number(settlement.probability),
        volatilityBps: Number(forecast.volatilityBps),
      }),
    };
  }
}
