import type { QuoteRequest, VenueQuote } from "./venueAdapter.js";

export type InstitutionalRfqProviderName = "wintermute" | "cumberland" | "b2c2" | "gsr";

export interface RfqProviderConfig {
  provider: InstitutionalRfqProviderName;
  apiUrl: string;
  apiKey: string;
  signingSecret: string;
  executableQuoteSupport: boolean;
  calldataExecutionMode: boolean;
  reliability: number;
  maxNotionalUsd: string;
}

export interface RfqProviderStatus {
  provider: InstitutionalRfqProviderName;
  configured: boolean;
  apiUrlConfigured: boolean;
  apiKeyConfigured: boolean;
  signingSecretConfigured: boolean;
  executableQuoteSupport: boolean;
  calldataExecutionMode: boolean;
}

export interface ExecutableRfqQuote {
  provider: InstitutionalRfqProviderName;
  quoteId: string;
  assetIn: string;
  assetOut: string;
  amountIn: string;
  amountOut: string;
  calldata: string;
  expiry: string;
  signature: string;
  executable: true;
  transaction: {
    to: string;
    data: string;
    valueWei: string;
    gasLimit?: string;
  };
  route: string[];
  gasCostUsd: string;
  slippageBps: number;
  liquidityDepth: string;
  failureProbability: number;
  partialFillSupported: boolean;
  fillableAmount: string;
  makerFillGuarantee: boolean;
  settlementDeadline: string;
  privateSettlementChannel?: string;
  requestNonce: string;
  responseTimestamp?: string;
  raw: Record<string, unknown>;
}

export interface RfqProviderFailure {
  provider: InstitutionalRfqProviderName;
  reason:
    | "not_configured"
    | "http_error"
    | "network_error"
    | "no_liquidity"
    | "expired_quote"
    | "invalid_signature"
    | "slippage_bounds_exceeded"
    | "missing_executable_calldata"
    | "nonce_mismatch"
    | "liquidity_unavailable"
    | "invalid_response";
  detail: string;
}

export interface RfqAdapterQuoteResult {
  provider: InstitutionalRfqProviderName;
  quote?: ExecutableRfqQuote;
  failure?: RfqProviderFailure;
}

export interface InstitutionalRfqAdapter {
  readonly provider: InstitutionalRfqProviderName;
  status(): RfqProviderStatus;
  requestQuote(request: QuoteRequest): Promise<RfqAdapterQuoteResult>;
}

export interface RfqAggregationResult {
  requestedProviders: InstitutionalRfqProviderName[];
  quotes: ExecutableRfqQuote[];
  failures: RfqProviderFailure[];
}

export interface ScoredRfqQuote {
  quote: ExecutableRfqQuote;
  score: number;
  components: {
    outputScore: number;
    gasPenalty: number;
    slippagePenalty: number;
    failurePenalty: number;
    expiryPenalty: number;
    guaranteeBonus: number;
    privateSettlementBonus: number;
  };
}

export interface RfqSelectionResult {
  selected?: ExecutableRfqQuote;
  scored: ScoredRfqQuote[];
  unavailable: RfqProviderFailure[];
}

export function executableQuoteToVenueQuote(quote: ExecutableRfqQuote): VenueQuote {
  return {
    quoteId: quote.quoteId,
    venue: "rfq",
    liquiditySource: `institutional:${quote.provider}`,
    route: quote.route,
    inputAmount: quote.amountIn,
    outputAmount: quote.amountOut,
    effectivePrice: Number(quote.amountIn) > 0 ? String(Number(quote.amountOut) / Number(quote.amountIn)) : "0",
    gasCostUsd: quote.gasCostUsd,
    slippageBps: quote.slippageBps,
    liquidityDepth: quote.liquidityDepth,
    failureProbability: quote.failureProbability,
    expiresAt: quote.expiry,
    privateSettlement: true,
    metadata: {
      provider: quote.provider,
      executable: true,
      signedExecutableQuote: true,
      signedRfq: true,
      makerFillGuarantee: quote.makerFillGuarantee,
      settlementDeadline: quote.settlementDeadline,
      partialFillSupported: quote.partialFillSupported,
      fillableAmount: quote.fillableAmount,
      privateSettlementChannel: quote.privateSettlementChannel ?? `${quote.provider}-private-rfq`,
      transaction: quote.transaction,
      calldata: quote.calldata,
      requestNonce: quote.requestNonce,
      responseTimestamp: quote.responseTimestamp,
      raw: {
        ...quote.raw,
        provider: quote.provider,
        transaction: quote.transaction,
        quoteSignature: quote.signature,
        expiresAt: quote.expiry,
      },
    },
  };
}
