export interface HiddenLiquidity {
  providerId: string;
  asset: string;
  maxSize: string;
  minSize: string;
}

export class HiddenLiquidityPool {
  providers(asset: string): HiddenLiquidity[] {
    const raw = process.env.HIDDEN_LIQUIDITY_JSON;
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) throw new Error("HIDDEN_LIQUIDITY_JSON must be an array");
    return parsed
      .map((item) => item as Record<string, unknown>)
      .filter((item) => String(item.asset ?? "").toUpperCase() === asset.toUpperCase())
      .map((item) => ({
        providerId: String(item.providerId ?? "hidden-provider"),
        asset: String(item.asset),
        maxSize: String(item.maxSize ?? "0"),
        minSize: String(item.minSize ?? "0"),
      }));
  }
}
