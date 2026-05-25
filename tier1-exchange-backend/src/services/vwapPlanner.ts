import type { VenueQuote } from "./venueAdapter.js";
import type { TwapSlice } from "./twapExecutor.js";

export class VwapPlanner {
  redistribute(slices: TwapSlice[], quotes: VenueQuote[]): TwapSlice[] {
    if (quotes.length === 0 || slices.length <= 1) return slices;
    const bestDepth = Math.max(...quotes.map((quote) => Number(quote.liquidityDepth || 0)), 1);
    return slices.map((slice, index) => {
      const liquidityWeight = Math.max(0.5, Math.min(1.5, Number(quotes[index % quotes.length]?.liquidityDepth ?? bestDepth) / bestDepth));
      return {
        ...slice,
        slippageBps: Math.round(slice.slippageBps * (2 - liquidityWeight)),
      };
    });
  }
}
