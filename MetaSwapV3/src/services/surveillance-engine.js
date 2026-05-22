export class SurveillanceEngine {
  constructor({ complianceHub, eventBus }) {
    this.complianceHub = complianceHub;
    this.eventBus = eventBus;
    this.activity = new Map();
  }

  recordTrade(trade) {
    const key = `${trade.userId}:${trade.symbol}`;
    const rows = this.activity.get(key) ?? [];
    rows.push({ side: trade.side, amount: trade.amount, price: trade.price, createdAt: Date.now() });
    this.activity.set(key, rows.slice(-100));
    const alert = this.detect(key, rows);
    if (alert) {
      this.complianceHub.openCase("MARKET_ABUSE", trade.userId, alert.reason, alert.severity);
      this.eventBus.publish("SurveillanceAlertRaised", { tradeId: trade.id, ...alert });
    }
    return alert;
  }

  detect(key, rows) {
    if (rows.length < 6) return null;
    const recent = rows.filter((row) => Date.now() - row.createdAt < 60_000);
    const buys = recent.filter((row) => row.side === "buy").length;
    const sells = recent.filter((row) => row.side === "sell").length;
    if (recent.length >= 10) return { reason: "HIGH_VELOCITY_TRADING", severity: "medium" };
    if (buys >= 3 && sells >= 3) return { reason: "POTENTIAL_WASH_PATTERN", severity: "high" };
    return null;
  }
}
