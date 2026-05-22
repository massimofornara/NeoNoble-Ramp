export class AssetRegistry {
  constructor(store) {
    this.store = store;
    this.assets = new Map();
    for (const asset of this.store?.loadAssets?.() ?? []) {
      this.assets.set(asset.symbol, asset);
    }
  }

  register(asset) {
    const normalized = {
      status: "active",
      lifecycle: "liquid",
      requiredTier: "basic",
      allowedJurisdictions: ["EU", "US", "UK", "ROW"],
      riskTier: "low",
      type: "crypto",
      ...asset
    };
    this.assets.set(normalized.symbol, normalized);
    this.store?.saveAsset?.(normalized);
    return normalized;
  }

  get(symbol) {
    const asset = this.assets.get(symbol);
    if (!asset) throw new Error(`Unknown asset ${symbol}`);
    return asset;
  }

  list() {
    return [...this.assets.values()];
  }
}
