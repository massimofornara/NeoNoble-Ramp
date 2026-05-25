import { MakerQuoteBook } from "./makerQuoteBook.js";
import { OtcLiquidityProvider } from "./otcLiquidityProvider.js";
import { RouteScorer, type ScoredRoute } from "./routeScorer.js";
import type { QuoteRequest, VenueQuote } from "./venueAdapter.js";

export interface RfqDecision {
  required: boolean;
  preferred: boolean;
  quotes: VenueQuote[];
  selected?: ScoredRoute;
}

export class RfqEngine {
  constructor(
    private readonly quoteBook = new MakerQuoteBook(),
    private readonly provider = new OtcLiquidityProvider(),
    private readonly scorer = new RouteScorer(),
  ) {}

  async requestForIntent(request: QuoteRequest): Promise<RfqDecision> {
    const amount = Number(request.amount);
    const required = amount > 100_000;
    const preferred = amount > 20_000;
    if (amount <= 5_000) return { required: false, preferred: false, quotes: [] };
    const makers = this.quoteBook.makers().filter((maker) => Number(maker.maxNotional || 0) === 0 || Number(maker.maxNotional) >= Number(request.expectedToAmount ?? request.amount));
    const settled = await Promise.allSettled(makers.map((maker) => this.provider.requestQuote(maker, request)));
    const quotes = settled
      .filter((result): result is PromiseFulfilledResult<VenueQuote | undefined> => result.status === "fulfilled")
      .map((result) => result.value)
      .filter((quote): quote is VenueQuote => Boolean(quote));
    const ranked = this.scorer.score(quotes);
    if (required && ranked.length === 0) {
      throw new Error("RFQ_REQUIRED_NO_MAKER_QUOTE: >100k NENO intents require a real maker quote");
    }
    return { required, preferred, quotes, selected: ranked[0] };
  }
}
