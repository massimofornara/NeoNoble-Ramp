import type { VenueQuote } from "./venueAdapter.js";

export interface ExecutionMarketAnalytics {
  volatilityBps: number;
  availableDepth: string;
  gasPressure: "low" | "normal" | "high";
  quoteCount: number;
}

export class ExecutionAnalytics {
  summarize(quotes: VenueQuote[]): ExecutionMarketAnalytics {
    const prices = quotes.map((quote) => Number(quote.effectivePrice)).filter((value) => Number.isFinite(value) && value > 0);
    const avg = prices.length > 0 ? prices.reduce((sum, value) => sum + value, 0) / prices.length : 0;
    const variance = prices.length > 0 ? prices.reduce((sum, value) => sum + (value - avg) ** 2, 0) / prices.length : 0;
    const volatilityBps = avg > 0 ? Math.round((Math.sqrt(variance) / avg) * 10_000) : 0;
    const depth = quotes.reduce((sum, quote) => sum + Number(quote.liquidityDepth || 0), 0);
    const gas = quotes.reduce((sum, quote) => sum + Number(quote.gasCostUsd || 0), 0) / Math.max(1, quotes.length);
    return {
      volatilityBps,
      availableDepth: String(depth),
      gasPressure: gas > 100 ? "high" : gas > 20 ? "normal" : "low",
      quoteCount: quotes.length,
    };
  }
}
