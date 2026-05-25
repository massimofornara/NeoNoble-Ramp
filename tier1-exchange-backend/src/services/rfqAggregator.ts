import { B2C2Adapter } from "./b2c2Adapter.js";
import { CumberlandAdapter } from "./cumberlandAdapter.js";
import { GSRAdapter } from "./gsrAdapter.js";
import type { InstitutionalRfqAdapter, RfqAggregationResult, RfqProviderStatus } from "./institutionalRfqTypes.js";
import type { QuoteRequest } from "./venueAdapter.js";
import { WintermuteAdapter } from "./wintermuteAdapter.js";

export class RFQAggregator {
  constructor(
    private readonly adapters: InstitutionalRfqAdapter[] = [new WintermuteAdapter(), new CumberlandAdapter(), new B2C2Adapter(), new GSRAdapter()],
  ) {}

  statuses(): RfqProviderStatus[] {
    return this.adapters.map((adapter) => adapter.status());
  }

  configuredProviders(): RfqProviderStatus[] {
    return this.statuses().filter((status) => status.configured);
  }

  async aggregate(request: QuoteRequest): Promise<RfqAggregationResult> {
    const configured = this.adapters.filter((adapter) => adapter.status().configured);
    const settled = await Promise.allSettled(configured.map((adapter) => adapter.requestQuote(request)));
    const results = settled.map((result, index) => {
      if (result.status === "fulfilled") return result.value;
      const provider = configured[index]?.provider ?? "wintermute";
      return {
        provider,
        failure: {
          provider,
          reason: "network_error" as const,
          detail: result.reason instanceof Error ? result.reason.message : String(result.reason),
        },
      };
    });
    return {
      requestedProviders: configured.map((adapter) => adapter.provider),
      quotes: results.map((result) => result.quote).filter((quote): quote is NonNullable<typeof quote> => Boolean(quote)),
      failures: results.map((result) => result.failure).filter((failure): failure is NonNullable<typeof failure> => Boolean(failure)),
    };
  }
}
