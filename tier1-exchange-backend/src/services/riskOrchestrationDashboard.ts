import type { AsyncRiskEngine } from "./asyncRiskEngine.js";

export class RiskOrchestrationDashboard {
  constructor(private readonly risk: AsyncRiskEngine) {}

  status(sampleAccount = "system", sampleNotional = 0): Record<string, unknown> {
    return {
      asyncRisk: this.risk.score(sampleAccount, sampleNotional),
      engine: this.risk.status(),
      queueMode: "delayed-review",
      postTradeSurveillance: true,
    };
  }
}
