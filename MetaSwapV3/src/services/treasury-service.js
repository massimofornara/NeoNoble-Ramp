export class TreasuryService {
  constructor({ ledger, pricingEngine, eventBus }) {
    this.ledger = ledger;
    this.pricingEngine = pricingEngine;
    this.eventBus = eventBus;
    this.capitalLimitsUsd = new Map([
      ["BTC", 2_000_000],
      ["ETH", 2_000_000],
      ["SOL", 1_000_000],
      ["default", 500_000]
    ]);
  }

  exposure(symbol) {
    const inventory = this.ledger.available("platform", "inventory", symbol);
    const usd = inventory * this.pricingEngine.usdValue(symbol);
    const limit = this.capitalLimitsUsd.get(symbol) ?? this.capitalLimitsUsd.get("default");
    return {
      symbol,
      inventory,
      usd,
      limit,
      utilization: limit > 0 ? Math.abs(usd / limit) : 1
    };
  }

  capitalAllocation(symbol, quoteAsset) {
    const exposure = this.exposure(symbol);
    const quoteOwner = quoteAsset === "EUR" || quoteAsset === "USD" ? "treasury" : "inventory";
    const treasuryQuote = this.ledger.available("platform", quoteOwner, quoteAsset);
    const quoteUsd = treasuryQuote * this.pricingEngine.usdValue(quoteAsset);
    const status = quoteUsd <= 0 ? "blocked" : "active";
    return {
      bucket: `${symbol}-${quoteAsset}-principal`,
      status,
      exposure,
      quoteUsd
    };
  }

  stressScore(symbol) {
    const exposure = this.exposure(symbol);
    return Math.min(1, Number(exposure.utilization.toFixed(6)));
  }

  stressTest(symbol, shockPercent = 0.25) {
    const exposure = this.exposure(symbol);
    const lossUsd = Math.abs(exposure.usd * shockPercent);
    const afterShockUtilization = exposure.limit > 0 ? Math.abs((exposure.usd - lossUsd) / exposure.limit) : 1;
    const result = { symbol, shockPercent, lossUsd, afterShockUtilization, pass: afterShockUtilization < 0.9 };
    this.eventBus.publish("LiquidityStressTestCompleted", result);
    return result;
  }
}
