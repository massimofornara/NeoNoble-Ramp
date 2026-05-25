import type { EventBus } from "../core/types.js";
import { ComplianceQueue } from "./complianceQueue.js";
import { SurveillanceService } from "./surveillanceService.js";

export interface AsyncRiskDecision {
  riskScore: number;
  tier: "low" | "medium" | "high" | "review";
  delayedReview: boolean;
  approvalRoute: "auto" | "staged-compliance" | "large-order-desk";
  executionThrottle: "none" | "adaptive" | "treasury-aware";
  volatilityAware: boolean;
}

export class AsyncRiskEngine {
  constructor(
    private readonly bus: EventBus,
    private readonly complianceQueue = new ComplianceQueue(),
    private readonly surveillance = new SurveillanceService(),
  ) {}

  registerConsumers(): void {
    this.bus.subscribe("execution.intent_created", "async-risk.intent-created", async (event) => {
      const decision = this.score(String(event.payload.accountId), Number(event.payload.expectedToAmount ?? event.payload.fromAmount ?? 0));
      if (decision.delayedReview) {
        this.complianceQueue.enqueue({
          intentId: event.transactionId,
          accountId: String(event.payload.accountId),
          riskScore: decision.riskScore,
          reason: `async_risk_${decision.tier}`,
        });
      }
    });
  }

  score(accountId: string, notional: number): AsyncRiskDecision {
    const adaptiveLimit = this.adaptiveNotionalLimit();
    const notionalScore = Math.min(1, notional / adaptiveLimit);
    const surveillanceScore = this.surveillance.abnormalExecutionScore(accountId);
    const volatilityScore = Math.min(1, Number(process.env.MARKET_VOLATILITY_BPS ?? 0) / Number(process.env.ASYNC_RISK_VOLATILITY_LIMIT_BPS ?? 1500));
    const treasuryUtilization = Math.min(1, Number(process.env.TREASURY_UTILIZATION_BPS ?? 0) / 10_000);
    const riskScore = Math.max(notionalScore, surveillanceScore, volatilityScore, treasuryUtilization);
    const tier = riskScore > 0.9 ? "review" : riskScore > 0.7 ? "high" : riskScore > 0.35 ? "medium" : "low";
    return {
      riskScore,
      tier,
      delayedReview: tier === "high" || tier === "review",
      approvalRoute: tier === "review" ? "large-order-desk" : tier === "high" ? "staged-compliance" : "auto",
      executionThrottle: tier === "review" ? "treasury-aware" : tier === "high" ? "adaptive" : "none",
      volatilityAware: true,
    };
  }

  status(): Record<string, unknown> {
    return {
      mode: "fully-async-institutional-risk",
      adaptiveNotionalLimit: String(this.adaptiveNotionalLimit()),
      stagedComplianceQueue: this.complianceQueue.pending(),
      marketVolatilityBps: process.env.MARKET_VOLATILITY_BPS ?? "0",
      treasuryUtilizationBps: process.env.TREASURY_UTILIZATION_BPS ?? "0",
      hardCircuitBreakerOnly: true,
    };
  }

  private adaptiveNotionalLimit(): number {
    const base = Number(process.env.ASYNC_RISK_NOTIONAL_LIMIT ?? 5_000_000);
    const volatilityBps = Number(process.env.MARKET_VOLATILITY_BPS ?? 0);
    const volatilityPenalty = Math.min(0.75, volatilityBps / 10_000);
    return Math.max(1, base * (1 - volatilityPenalty));
  }
}
