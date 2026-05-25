import { ExposureMonitor } from "./exposureMonitor.js";
import { HedgingEngine } from "./hedgingEngine.js";
import { MarginEngine } from "./marginEngine.js";

export class PortfolioEngine {
  constructor(
    private readonly exposureMonitor = new ExposureMonitor(),
    private readonly marginEngine = new MarginEngine(),
    private readonly hedgingEngine = new HedgingEngine(),
  ) {}

  assess(asset: string, amount: string, notionalUsd: string): Record<string, unknown> {
    const exposure = this.exposureMonitor.exposure(asset, amount);
    return {
      exposure,
      margin: this.marginEngine.requirement(notionalUsd),
      hedge: this.hedgingEngine.hedge(asset, notionalUsd),
      inventoryVaR: {
        confidence: process.env.VAR_CONFIDENCE ?? "0.99",
        valueUsd: String(Number(notionalUsd) * Number(process.env.VAR_RATE ?? 0.03)),
      },
      liquidityStress: {
        stressMultiplier: process.env.LIQUIDITY_STRESS_MULTIPLIER ?? "2",
        stressedNotionalUsd: String(Number(notionalUsd) * Number(process.env.LIQUIDITY_STRESS_MULTIPLIER ?? 2)),
      },
    };
  }
}
