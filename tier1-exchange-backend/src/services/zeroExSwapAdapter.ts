import type { ExecutionVenueAdapter, QuoteRequest, VenueQuote } from "./venueAdapter.js";
import {
  appendQuery,
  asRecord,
  assetAddress,
  buildDexQuote,
  containsString,
  fetchJson,
  firstRecord,
  hasExecutableTransaction,
  rawInputAmount,
  routableAsset,
  stringField,
} from "./dexAdapterUtils.js";

const ZEROX_PRICE_URL = "https://api.0x.org/swap/allowance-holder/price";
const ZEROX_QUOTE_URL = "https://api.0x.org/swap/allowance-holder/quote";

export class ZeroExSwapAdapter implements ExecutionVenueAdapter {
  readonly venue = "0x" as const;

  async quote(request: QuoteRequest): Promise<VenueQuote | undefined> {
    const apiKey = process.env.ZEROX_API_KEY;
    if (!apiKey) return undefined;
    const taker = process.env.TREASURY_ADDRESS;
    if (!taker || !/^0x[a-fA-F0-9]{40}$/.test(taker)) {
      throw new Error("0x executable quote requires TREASURY_ADDRESS");
    }

    const headers = {
      "0x-api-key": apiKey,
      "0x-version": process.env.ZEROX_API_VERSION ?? "v2",
      accept: "application/json",
    };
    const price = await fetchJson(this.url(process.env.ZEROX_PRICE_URL ?? ZEROX_PRICE_URL, request, taker), headers, "0x price");
    const quote = await fetchJson(this.url(process.env.ZEROX_QUOTE_URL ?? ZEROX_QUOTE_URL, request, taker), headers, "0x quote");
    const transaction = firstRecord(quote.transaction, quote.tx);
    const allowanceTarget = allowanceTargetFrom(quote) ?? allowanceTargetFrom(price);
    const outputAmountRaw = stringField(quote, "buyAmount", "outputAmount", "toAmount") ?? stringField(price, "buyAmount", "outputAmount", "toAmount");
    const rfqEmbedded = containsString(quote, "0x_RFQ") || containsString(price, "0x_RFQ");
    const raw = {
      ...quote,
      price,
      transaction,
      allowanceTarget,
      provider: "0x",
    };

    return buildDexQuote({
      request,
      venue: this.venue,
      liquiditySource: rfqEmbedded ? "0x_RFQ" : "0x_SWAP",
      quoteId: stringField(quote, "quoteId", "zid"),
      route: [routableAsset(request.fromAsset, request.chainId), routableAsset(request.toAsset, request.chainId)],
      outputAmountRaw,
      gasCostUsd: "0",
      failureProbability: rfqEmbedded ? 0.01 : 0.03,
      privateSettlement: rfqEmbedded,
      expiresAt: stringField(quote, "expiry", "expiresAt"),
      metadata: {
        raw,
        executable: hasExecutableTransaction(raw),
        providerSlippageBps: request.slippageBps ?? Number(process.env.SWAP_SLIPPAGE_BPS ?? 75),
        rfqEmbedded,
        source: rfqEmbedded ? "0x_RFQ" : "0x_SWAP",
        signedExecutableQuote: rfqEmbedded,
        makerFillGuarantee: rfqEmbedded,
        partialFillSupported: true,
        calldataExecutionMode: true,
        allowanceTarget,
      },
    });
  }

  private url(base: string, request: QuoteRequest, taker: string): URL {
    const url = new URL(base);
    return appendQuery(url, {
      chainId: request.chainId,
      sellToken: assetAddress(request.fromAsset, request.chainId),
      buyToken: assetAddress(request.toAsset, request.chainId),
      sellAmount: rawInputAmount(request),
      taker,
      slippageBps: request.slippageBps ?? Number(process.env.SWAP_SLIPPAGE_BPS ?? 75),
    });
  }
}

function allowanceTargetFrom(value: Record<string, unknown>): string | undefined {
  const issues = asRecord(value.issues);
  const allowance = asRecord(issues.allowance);
  const candidate =
    stringField(value, "allowanceTarget", "approvalTarget", "spender") ??
    stringField(allowance, "spender", "allowanceTarget") ??
    stringField(asRecord(value.transaction), "allowanceTarget", "approvalTarget", "spender");
  return candidate && /^0x[a-fA-F0-9]{40}$/.test(candidate) ? candidate : undefined;
}
