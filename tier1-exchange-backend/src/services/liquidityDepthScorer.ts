import type { VenueQuote } from "./venueAdapter.js";

export class LiquidityDepthScorer {
  depthScore(quote: VenueQuote): number {
    const depth = Number(quote.liquidityDepth || 0);
    const output = Number(quote.outputAmount || 0);
    if (depth <= 0 || output <= 0) return 0;
    return Math.min(1, depth / Math.max(output, 1));
  }
}
