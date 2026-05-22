const median = (values) => {
  const sorted = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!sorted.length) throw new Error("No valid price sources");
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
};

export class PricingEngine {
  constructor({ assetRegistry, eventBus }) {
    this.assetRegistry = assetRegistry;
    this.eventBus = eventBus;
    this.oracleFeedsUsd = new Map([
      ["USD", [1]],
      ["EUR", [1.08, 1.079, 1.081]],
      ["USDT", [1, 0.999, 1.001]],
      ["BTC", [65000, 65120, 64880]],
      ["ETH", [3500, 3508, 3494]],
      ["BNB", [600, 602, 598]],
      ["MATIC", [0.75, 0.751, 0.749]],
      ["SOL", [150, 151, 149.4]]
    ]);
    this.rfqMarksUsd = new Map();
    this.internalDemand = new Map();
  }

  setOracle(symbol, feedsUsd) {
    if (!feedsUsd) {
      this.oracleFeedsUsd.delete(symbol);
      return;
    }
    this.oracleFeedsUsd.set(symbol, feedsUsd);
  }

  setRfqMark(symbol, priceUsd) {
    this.rfqMarksUsd.set(symbol, priceUsd);
  }

  recordDemand(symbol, signedUsdNotional) {
    this.internalDemand.set(symbol, (this.internalDemand.get(symbol) ?? 0) + signedUsdNotional);
  }

  usdValue(symbol) {
    const asset = this.assetRegistry.get(symbol);
    if (this.oracleFeedsUsd.has(symbol)) return median(this.oracleFeedsUsd.get(symbol));
    const pricing = asset.pricing ?? {};
    return pricing.issuePriceUsd ?? pricing.navUsd ?? 1;
  }

  fairPriceUsd(symbol) {
    const asset = this.assetRegistry.get(symbol);
    const pricing = asset.pricing ?? {};
    const oracle = this.oracleFeedsUsd.has(symbol) ? median(this.oracleFeedsUsd.get(symbol)) : undefined;
    const rfq = this.rfqMarksUsd.get(symbol);
    const demandSignal = Math.max(-0.1, Math.min(0.1, (this.internalDemand.get(symbol) ?? 0) / 1_000_000));
    const issueOrNav = pricing.navUsd ?? pricing.issuePriceUsd ?? oracle ?? rfq ?? 1;

    const weights = oracle
      ? { oracle: 0.65, rfq: 0.15, demand: 0.05, issue: 0.15 }
      : { oracle: 0, rfq: rfq ? 0.4 : 0, demand: 0.1, issue: rfq ? 0.5 : 0.9 };

    const base =
      (weights.oracle * (oracle ?? 0)) +
      (weights.rfq * (rfq ?? issueOrNav)) +
      (weights.demand * issueOrNav * (1 + demandSignal)) +
      (weights.issue * issueOrNav);

    const riskDiscount = this.riskDiscount(asset);
    const inventoryAdjustment = pricing.inventoryAdjustmentUsd ?? 0;
    const fair = Math.max(0.00000001, base + inventoryAdjustment - riskDiscount);
    return Number(fair.toFixed(8));
  }

  midPrice(symbol, quoteAsset = "USD") {
    return Number((this.fairPriceUsd(symbol) / this.usdValue(quoteAsset)).toFixed(8));
  }

  quote({ symbol, quoteAsset, side, amount, userRisk = 0.05, inventoryRatio = 0 }) {
    const mid = this.midPrice(symbol, quoteAsset);
    const spread = this.spread({ symbol, amount, userRisk, inventoryRatio });
    const price = side === "buy" ? mid * (1 + spread) : mid * (1 - spread);
    return {
      symbol,
      quoteAsset,
      side,
      amount,
      mid,
      spread,
      price: Number(price.toFixed(8)),
      confidence: this.confidence(symbol)
    };
  }

  spread({ symbol, amount, userRisk, inventoryRatio }) {
    const asset = this.assetRegistry.get(symbol);
    const base = asset.lifecycle === "liquid" ? 0.0015 : 0.015;
    const volatility = asset.riskTier === "high" ? 0.03 : asset.riskTier === "medium" ? 0.01 : 0.003;
    const liquidity = asset.lifecycle === "liquid" ? 0.001 : asset.lifecycle === "hybrid" ? 0.008 : 0.02;
    const inventory = Math.abs(inventoryRatio) * 0.02;
    const compliance = userRisk * 0.03;
    const size = Math.min(0.02, amount / 1_000_000);
    return Number((base + volatility + liquidity + inventory + compliance + size).toFixed(6));
  }

  riskDiscount(asset) {
    if (asset.riskTier === "high") return (asset.pricing?.issuePriceUsd ?? 1) * 0.05;
    if (asset.riskTier === "medium") return (asset.pricing?.issuePriceUsd ?? 1) * 0.01;
    return 0;
  }

  confidence(symbol) {
    if (this.oracleFeedsUsd.has(symbol)) return "high";
    if (this.rfqMarksUsd.has(symbol)) return "medium";
    return "controlled";
  }
}
