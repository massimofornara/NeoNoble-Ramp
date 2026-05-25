import type { VenueQuote } from "./venueAdapter.js";

export class BlockTradeExecutor {
  executionEnvelope(quote: VenueQuote | undefined): Record<string, unknown> {
    if (!quote) {
      return {
        enabled: false,
        reason: "no_real_institutional_quote",
      };
    }
    return {
      enabled: true,
      quoteId: quote.quoteId,
      counterparty: quote.liquiditySource,
      privateSettlement: quote.privateSettlement,
      executable: Boolean(quote.metadata.executable),
      signedExecutableQuote: Boolean(quote.metadata.signedExecutableQuote),
      makerFillGuarantee: Boolean(quote.metadata.makerFillGuarantee),
      settlementDeadline: quote.metadata.settlementDeadline,
      settlementInstructionsPresent: Boolean(quote.metadata.settlementInstructions),
    };
  }
}
