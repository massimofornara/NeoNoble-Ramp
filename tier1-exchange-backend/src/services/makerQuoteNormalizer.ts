import type { MakerConnectivityResult } from "./makerConnectivity.js";
import type { VenueQuote } from "./venueAdapter.js";

export class MakerQuoteNormalizer {
  normalize(results: MakerConnectivityResult[]): VenueQuote[] {
    return results.map((result) => result.quote).filter((quote): quote is VenueQuote => Boolean(quote));
  }
}
