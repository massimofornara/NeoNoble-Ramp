import type { ExecutionVenueAdapter, QuoteRequest, VenueQuote } from "./venueAdapter.js";

export interface AggregatedQuotes {
  request: QuoteRequest;
  quotes: VenueQuote[];
  unavailableVenues: Array<{ venue: string; reason: string }>;
}

export class QuoteAggregator {
  constructor(private readonly adapters: ExecutionVenueAdapter[]) {}

  async aggregate(request: QuoteRequest): Promise<AggregatedQuotes> {
    const settled = await Promise.all(
      this.adapters.map(async (adapter) => {
        try {
          return { adapter, quote: await adapter.quote(request) };
        } catch (error) {
          return { adapter, error };
        }
      }),
    );
    const quotes: VenueQuote[] = [];
    const unavailableVenues: Array<{ venue: string; reason: string }> = [];
    for (const result of settled) {
      if ("error" in result) {
        unavailableVenues.push({ venue: result.adapter.venue, reason: result.error instanceof Error ? result.error.message : String(result.error) });
      } else if (result.quote) {
        quotes.push(result.quote);
      } else {
        unavailableVenues.push({ venue: result.adapter.venue, reason: "not_configured_or_no_quote" });
      }
    }
    return { request, quotes, unavailableVenues };
  }
}
