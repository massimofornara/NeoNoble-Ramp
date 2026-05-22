export class InternalMarketMaker {
  constructor({ pricingEngine, liquidityEngine, treasuryService, eventBus }) {
    this.pricingEngine = pricingEngine;
    this.liquidityEngine = liquidityEngine;
    this.treasuryService = treasuryService;
    this.eventBus = eventBus;
  }

  quote({ symbol, quoteAsset, side, amount, userRisk }) {
    const allocation = this.treasuryService.capitalAllocation(symbol, quoteAsset);
    const maxSize = this.liquidityEngine.capacity(symbol, quoteAsset, side);
    const stress = this.treasuryService.stressScore(symbol);
    const wouldIncreaseInventory = side === "sell";
    const capitalBlocked = wouldIncreaseInventory && allocation.status === "blocked";
    if (amount > maxSize || capitalBlocked) {
      return {
        rejected: true,
        provider: "internal-market-maker",
        reason: "INTERNAL_MARKET_MAKER_LIMIT",
        maxSize,
        stress
      };
    }

    const quote = this.pricingEngine.quote({
      symbol,
      quoteAsset,
      side,
      amount,
      userRisk,
      inventoryRatio: this.liquidityEngine.inventoryRatio(symbol)
    });
    const result = {
      ...quote,
      provider: "internal-market-maker",
      ttlMs: Math.max(750, Math.floor(5000 * (1 - stress))),
      maxSize,
      capitalBucket: allocation.bucket,
      stress
    };
    this.eventBus.publish("InternalMarketMakerQuoteGenerated", result);
    return result;
  }
}
