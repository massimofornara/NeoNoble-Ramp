import { LiquidityDepthScorer } from "./liquidityDepthScorer.js";
import type { VenueQuote } from "./venueAdapter.js";

export class CounterpartySelector {
  constructor(private readonly depthScorer = new LiquidityDepthScorer()) {}

  select(quotes: VenueQuote[]): VenueQuote | undefined {
    return quotes.filter((quote) => Date.parse(quote.expiresAt) > Date.now()).sort((left, right) => this.score(right) - this.score(left))[0];
  }

  private score(quote: VenueQuote): number {
    return Number(quote.outputAmount) * this.depthScorer.depthScore(quote) * (1 - quote.failureProbability);
  }
}
