import type { RfqAggregationResult, RfqSelectionResult, ScoredRfqQuote } from "./institutionalRfqTypes.js";
import { RFQScoreEngine } from "./rfqScoreEngine.js";

export class RFQExecutionSelector {
  private readonly reservedFillKeys = new Set<string>();

  constructor(private readonly scorer = new RFQScoreEngine()) {}

  select(result: RfqAggregationResult, idempotencyKey?: string): RfqSelectionResult {
    const scored = this.scorer.score(result.quotes).filter((item) => this.quoteStillExecutable(item));
    const selected = scored.find((item) => !this.reservedFillKeys.has(this.fillKey(item, idempotencyKey)))?.quote;
    if (selected) this.reservedFillKeys.add(`${selected.provider}:${selected.quoteId}:${idempotencyKey ?? "default"}`);
    return {
      selected,
      scored,
      unavailable: result.failures,
    };
  }

  private quoteStillExecutable(item: ScoredRfqQuote): boolean {
    const quote = item.quote;
    return quote.executable && Date.parse(quote.expiry) > Date.now() && /^0x[a-fA-F0-9]{40}$/.test(quote.transaction.to) && /^0x([a-fA-F0-9]{2})*$/.test(quote.transaction.data);
  }

  private fillKey(item: ScoredRfqQuote, idempotencyKey?: string): string {
    return `${item.quote.provider}:${item.quote.quoteId}:${idempotencyKey ?? "default"}`;
  }
}
