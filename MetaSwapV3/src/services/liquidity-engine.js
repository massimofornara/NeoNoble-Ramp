export class InternalLiquidityEngine {
  constructor({ ledger, pricingEngine, eventBus }) {
    this.ledger = ledger;
    this.pricingEngine = pricingEngine;
    this.eventBus = eventBus;
    this.inventoryLimits = new Map();
    this.defaultLimitUsd = 500_000;
  }

  setLimit(symbol, limitUsd) {
    this.inventoryLimits.set(symbol, limitUsd);
  }

  inventoryRatio(symbol) {
    const inventory = this.ledger.available("platform", "inventory", symbol);
    const usd = inventory * this.pricingEngine.usdValue(symbol);
    const limit = this.inventoryLimits.get(symbol) ?? this.defaultLimitUsd;
    return Math.max(-1, Math.min(1, usd / limit));
  }

  capacity(symbol, quoteAsset, side) {
    const limitUsd = this.inventoryLimits.get(symbol) ?? this.defaultLimitUsd;
    if (side === "buy") {
      const inventory = this.ledger.available("platform", "inventory", symbol);
      return Math.min(inventory, limitUsd / this.pricingEngine.usdValue(symbol));
    }
    const quoteOwner = quoteAsset === "EUR" || quoteAsset === "USD" ? "treasury" : "inventory";
    const cash = this.ledger.available("platform", quoteOwner, quoteAsset);
    return cash / this.pricingEngine.midPrice(symbol, quoteAsset);
  }

  quote({ symbol, quoteAsset, side, amount, userRisk }) {
    const maxSize = this.capacity(symbol, quoteAsset, side);
    if (amount > maxSize) {
      return { rejected: true, reason: "INTERNAL_INVENTORY_CAPACITY_EXCEEDED", maxSize };
    }
    const quote = this.pricingEngine.quote({
      symbol,
      quoteAsset,
      side,
      amount,
      userRisk,
      inventoryRatio: this.inventoryRatio(symbol)
    });
    const response = { ...quote, provider: "internal-liquidity-engine", ttlMs: 5000, maxSize };
    this.eventBus.publish("InternalQuoteCreated", response);
    return response;
  }
}
