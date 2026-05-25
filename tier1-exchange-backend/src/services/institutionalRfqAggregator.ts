import { BlockTradeExecutor } from "./blockTradeExecutor.js";
import { executableQuoteToVenueQuote, type RfqProviderStatus } from "./institutionalRfqTypes.js";
import { RFQAggregator } from "./rfqAggregator.js";
import { RFQExecutionSelector } from "./rfqExecutionSelector.js";
import type { QuoteRequest, VenueQuote } from "./venueAdapter.js";

export interface InstitutionalRfqDecision {
  requestedMakers: string[];
  unavailable: Array<{ maker: string; reason: string }>;
  quotes: VenueQuote[];
  selected?: VenueQuote;
  selectedExecutable?: VenueQuote;
  blockTrade: Record<string, unknown>;
  providerStatuses: RfqProviderStatus[];
}

export class InstitutionalRfqAggregator {
  constructor(
    private readonly gateway = new RFQAggregator(),
    private readonly selector = new RFQExecutionSelector(),
    private readonly blockTradeExecutor = new BlockTradeExecutor(),
  ) {}

  async aggregate(request: QuoteRequest): Promise<InstitutionalRfqDecision> {
    const aggregation = await this.gateway.aggregate(request);
    const selection = this.selector.select(aggregation, request.intentId);
    const quotes = aggregation.quotes.map(executableQuoteToVenueQuote);
    const selectedExecutable = selection.selected ? executableQuoteToVenueQuote(selection.selected) : undefined;
    const selected = selectedExecutable;
    return {
      requestedMakers: aggregation.requestedProviders,
      unavailable: aggregation.failures.map((failure) => ({ maker: failure.provider, reason: `${failure.reason}:${failure.detail}` })),
      quotes,
      selected,
      selectedExecutable,
      blockTrade: this.blockTradeExecutor.executionEnvelope(selected),
      providerStatuses: this.gateway.statuses(),
    };
  }
}
