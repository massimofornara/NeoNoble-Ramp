export class AnomalyDetectionService {
  constructor({ eventBus, ledger, developerPlatform, revenueEngine }) {
    this.eventBus = eventBus;
    this.ledger = ledger;
    this.developerPlatform = developerPlatform;
    this.revenueEngine = revenueEngine;
  }

  report() {
    const events = this.eventBus.tail(1000);
    const usage = this.developerPlatform.usage;
    const revenue = this.revenueEngine.summary({ targetMonthlyUsd: Number(process.env.REVENUE_TARGET_MONTHLY_USD ?? 1_000_000) });
    const signals = [];
    const errors = usage.filter((row) => row.status === "error").length;
    if (usage.length && errors / usage.length > 0.05) {
      signals.push({ severity: "high", code: "API_ERROR_RATE", value: errors / usage.length, action: "Shift RPC pool, inspect failing providers, apply circuit breaker." });
    }
    if (revenue.capturedRevenueUsd === 0) {
      signals.push({ severity: "medium", code: "NO_REVENUE_CAPTURED", action: "Prioritize enterprise pilots, paid API plans, issuer onboarding and tx relay activation." });
    }
    const rejectedOrders = events.filter((event) => event.type === "OrderRejected").length;
    if (rejectedOrders > 10) {
      signals.push({ severity: "medium", code: "ORDER_REJECTION_SPIKE", value: rejectedOrders, action: "Inspect risk rules and UX funding instructions." });
    }
    const feeAccounts = [...this.ledger.accounts.values()].filter((account) => account.ownerType === "platform" && account.ownerId === "fees").length;
    if (!feeAccounts) {
      signals.push({ severity: "low", code: "NO_FEE_ACCOUNTS", action: "Run paid flows or API metering before revenue sweep can execute." });
    }
    return {
      generatedAt: new Date().toISOString(),
      eventCount: events.length,
      apiUsageCount: usage.length,
      feeAccountCount: feeAccounts,
      signals,
      status: signals.some((signal) => signal.severity === "high") ? "attention_required" : "normal"
    };
  }
}
