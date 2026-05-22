export class RfqEngine {
  constructor({ pricingEngine, liquidityEngine, eventBus, internalMarketMaker, marketMakerAdapter }) {
    this.pricingEngine = pricingEngine;
    this.liquidityEngine = liquidityEngine;
    this.eventBus = eventBus;
    this.internalMarketMaker = internalMarketMaker;
    this.marketMakerAdapter = marketMakerAdapter;
  }

  async requestQuote({ userRisk, symbol, quoteAsset, side, amount }) {
    const quotes = [];
    const internal = this.internalMarketMaker?.quote({ symbol, quoteAsset, side, amount, userRisk })
      ?? this.liquidityEngine.quote({ symbol, quoteAsset, side, amount, userRisk });
    if (!internal.rejected) quotes.push(internal);

    try {
      const external = await this.marketMakerAdapter?.requestQuote({ symbol, quoteAsset, side, amount });
      if (external?.price) {
        quotes.push({
          provider: external.provider ?? "market-maker",
          symbol,
          quoteAsset,
          side,
          amount,
          price: Number(external.price),
          spread: Number(external.spread ?? 0),
          confidence: external.confidence ?? "external",
          ttlMs: Number(external.ttlMs ?? 3000),
          maxSize: Number(external.maxSize ?? amount)
        });
      }
    } catch (error) {
      this.eventBus.publish("MarketMakerQuoteUnavailable", { symbol, quoteAsset, side, amount, error: error.message });
    }

    const executable = quotes.filter((q) => !q.rejected && q.maxSize >= amount);
    if (!executable.length) throw new Error("No executable RFQ quote");
    executable.sort((a, b) => side === "buy" ? a.price - b.price : b.price - a.price);
    const best = executable[0];
    this.pricingEngine.setRfqMark(symbol, best.price * this.pricingEngine.usdValue(quoteAsset));
    this.eventBus.publish("RfqQuoteSelected", { symbol, side, amount, best, quoteCount: executable.length });
    return best;
  }
}
