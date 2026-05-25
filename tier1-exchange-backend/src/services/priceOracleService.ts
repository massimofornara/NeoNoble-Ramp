import { createHash } from "node:crypto";

export interface PriceSnapshot {
  pair: string;
  price: string;
  source: "coingecko" | "dexscreener" | "deterministic";
  capturedAt: string;
  replayKey: string;
  raw: Record<string, unknown>;
}

export class PriceOracleService {
  private readonly cache = new Map<string, PriceSnapshot>();

  async wbnbUsdtSnapshot(): Promise<PriceSnapshot> {
    return this.assetUsdtSnapshot("WBNB");
  }

  async assetUsdtSnapshot(asset: "WBNB" | "ETH" | "BTC"): Promise<PriceSnapshot> {
    const pair = `${asset}/USDT`;
    const cached = this.cache.get(pair);
    if (cached && Date.now() - Date.parse(cached.capturedAt) < Number(process.env.ORACLE_CACHE_TTL_MS ?? 30_000)) {
      return cached;
    }
    const mode = String(process.env.PRICE_DISCOVERY_MODE ?? "deterministic").toLowerCase();
    if (mode === "real" || process.env.COINGECKO_API_BASE_URL || process.env.DEXSCREENER_API_BASE_URL) {
      const external = (await this.fromCoinGecko(asset)) ?? (asset === "WBNB" ? await this.fromDexScreener() : null);
      if (external) {
        this.cache.set(pair, external);
        return external;
      }
      if (mode === "real") {
        if (process.env.PRICE_DISCOVERY_ALLOW_REPLAY_FALLBACK === "1") {
          const replayFallback = this.snapshot(pair, deterministicPrice(asset), "deterministic", {
            reason: "replay-safe pricing fallback after external oracle miss",
            oracleMode: mode,
          });
          this.cache.set(pair, replayFallback);
          return replayFallback;
        }
        throw new Error(`PRICE_DISCOVERY_MODE=real requires a successful ${pair} price snapshot`);
      }
    }
    const deterministic = this.snapshot(pair, deterministicPrice(asset), "deterministic", {
      reason: "local deterministic fallback",
    });
    this.cache.set(pair, deterministic);
    return deterministic;
  }

  async legacyWbnbUsdtSnapshot(): Promise<PriceSnapshot> {
    const pair = "WBNB/USDT";
    const cached = this.cache.get(pair);
    if (cached && Date.now() - Date.parse(cached.capturedAt) < Number(process.env.ORACLE_CACHE_TTL_MS ?? 30_000)) {
      return cached;
    }
    const mode = String(process.env.PRICE_DISCOVERY_MODE ?? "deterministic").toLowerCase();
    if (mode === "real" || process.env.COINGECKO_API_BASE_URL || process.env.DEXSCREENER_API_BASE_URL) {
      const external = await this.tryExternalWbnbPrice();
      if (external) {
        this.cache.set(pair, external);
        return external;
      }
      if (mode === "real") {
        throw new Error("PRICE_DISCOVERY_MODE=real requires a successful CoinGecko or DEX Screener price snapshot");
      }
    }
    const deterministic = this.snapshot(pair, process.env.WBNB_USDT_PRICE ?? "1000", "deterministic", {
      reason: "local deterministic fallback",
    });
    this.cache.set(pair, deterministic);
    return deterministic;
  }

  private async tryExternalWbnbPrice(): Promise<PriceSnapshot | null> {
    return (await this.fromCoinGecko("WBNB")) ?? (await this.fromDexScreener());
  }

  private async fromCoinGecko(asset: "WBNB" | "ETH" | "BTC"): Promise<PriceSnapshot | null> {
    try {
      const base = process.env.COINGECKO_API_BASE_URL ?? "https://api.coingecko.com/api/v3";
      const id = process.env[`${asset}_COINGECKO_ID`] ?? coingeckoId(asset);
      const response = await fetch(`${base}/simple/price?ids=${encodeURIComponent(id)}&vs_currencies=usd`, {
        headers: process.env.COINGECKO_API_KEY ? { "x-cg-demo-api-key": process.env.COINGECKO_API_KEY } : {},
      });
      if (!response.ok) return null;
      const body = (await response.json()) as Record<string, { usd?: number }>;
      const price = body[id]?.usd;
      if (!price || !Number.isFinite(price)) return null;
      return this.snapshot(`${asset}/USDT`, String(price), "coingecko", body as Record<string, unknown>);
    } catch {
      return null;
    }
  }

  private async fromDexScreener(): Promise<PriceSnapshot | null> {
    try {
      const base = process.env.DEXSCREENER_API_BASE_URL ?? "https://api.dexscreener.com/latest/dex";
      const pairAddress = process.env.WBNB_USDT_DEXSCREENER_PAIR;
      if (!pairAddress) return null;
      const response = await fetch(`${base}/pairs/bsc/${encodeURIComponent(pairAddress)}`);
      if (!response.ok) return null;
      const body = (await response.json()) as { pair?: { priceUsd?: string } };
      const price = body.pair?.priceUsd;
      if (!price) return null;
      return this.snapshot("WBNB/USDT", price, "dexscreener", body as unknown as Record<string, unknown>);
    } catch {
      return null;
    }
  }

  private snapshot(pair: string, price: string, source: PriceSnapshot["source"], raw: Record<string, unknown>): PriceSnapshot {
    const capturedAt = new Date().toISOString();
    const replayKey = createHash("sha256").update(JSON.stringify({ pair, price, source, raw, capturedAt })).digest("hex");
    return { pair, price, source, capturedAt, replayKey, raw };
  }
}

function coingeckoId(asset: "WBNB" | "ETH" | "BTC"): string {
  if (asset === "ETH") return "ethereum";
  if (asset === "BTC") return "bitcoin";
  return "wbnb";
}

function deterministicPrice(asset: "WBNB" | "ETH" | "BTC"): string {
  if (asset === "ETH") return process.env.ETH_USDT_PRICE ?? "3000";
  if (asset === "BTC") return process.env.BTC_USDT_PRICE ?? "100000";
  return process.env.WBNB_USDT_PRICE ?? "1000";
}
