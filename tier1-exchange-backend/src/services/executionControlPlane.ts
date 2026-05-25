import type { EventStore, SettlementProofStore } from "../core/store.js";
import type { AsyncRiskEngine } from "./asyncRiskEngine.js";
import { LiquidityTelemetry } from "./liquidityTelemetry.js";
import { RiskOrchestrationDashboard } from "./riskOrchestrationDashboard.js";
import { SettlementAnalyticsEngine } from "./settlementAnalyticsEngine.js";
import { TreasuryCommandCenter } from "./treasuryCommandCenter.js";
import type { TreasuryEngine } from "./treasuryEngine.js";

export class ExecutionControlPlane {
  private readonly liquidityTelemetry: LiquidityTelemetry;
  private readonly settlementAnalytics: SettlementAnalyticsEngine;
  private readonly treasuryCommand: TreasuryCommandCenter;
  private readonly riskDashboard: RiskOrchestrationDashboard;

  constructor(events: EventStore, proofs: SettlementProofStore, treasury: TreasuryEngine, risk: AsyncRiskEngine) {
    this.liquidityTelemetry = new LiquidityTelemetry(events);
    this.settlementAnalytics = new SettlementAnalyticsEngine(events, proofs);
    this.treasuryCommand = new TreasuryCommandCenter(treasury);
    this.riskDashboard = new RiskOrchestrationDashboard(risk);
  }

  status(): Record<string, unknown> {
    return {
      exchangeOs: "NeoNoble Global Liquidity Fabric",
      executionMode: {
        flow: "continuous-production",
        artificialExecutionGates: "disabled",
        safetyControls: ["risk", "settlement", "reconciliation", "watchtower", "treasury", "mpc-custody"],
      },
      deterministicReplay: true,
      immutableAuditTrail: true,
      liquidity: this.liquidityTelemetry.snapshot(),
      treasury: this.treasuryCommand.status(),
      settlement: this.settlementAnalytics.report(),
      risk: this.riskDashboard.status(),
      capturedAt: new Date().toISOString(),
    };
  }
}
