import { createHmac, randomUUID } from "node:crypto";
import { appendQuery, asRecord, buildDexQuote, hasExecutableTransaction, rawInputAmount, stringField } from "./dexAdapterUtils.js";
import type { ExecutionVenueAdapter, QuoteRequest, VenueQuote } from "./venueAdapter.js";

export class DwfLiquidMarketsAdapter implements ExecutionVenueAdapter {
  readonly venue = "dwf" as const;

  static configStatus(): Record<string, unknown> {
    const enabled = process.env.DWF_LIQUIDITY_ENABLED === "true";
    return {
      provider: "dwf",
      enabled,
      configured: Boolean(enabled && (process.env.DWF_QUOTE_URL || process.env.DWF_API_URL) && process.env.DWF_API_KEY),
      quoteUrlConfigured: Boolean(process.env.DWF_QUOTE_URL || process.env.DWF_API_URL),
      apiKeyConfigured: Boolean(process.env.DWF_API_KEY),
      signingSecretConfigured: Boolean(process.env.DWF_SIGNING_SECRET),
      executableQuoteSupport: true,
      calldataExecutionMode: true,
      privateExecution: true,
    };
  }

  async quote(request: QuoteRequest): Promise<VenueQuote | undefined> {
    if (process.env.DWF_LIQUIDITY_ENABLED !== "true") return undefined;
    const endpoint = process.env.DWF_QUOTE_URL ?? process.env.DWF_API_URL;
    const apiKey = process.env.DWF_API_KEY;
    if (!endpoint || !apiKey) throw new Error("DWF_LIQUIDITY_ENABLED=true requires DWF_QUOTE_URL/DWF_API_URL and DWF_API_KEY");

    const body = JSON.stringify({
      requestId: request.intentId ?? randomUUID(),
      chainId: request.chainId,
      sellToken: request.fromAsset,
      buyToken: request.toAsset,
      sellAmount: request.amount,
      sellAmountRaw: rawInputAmount(request),
      expectedBuyAmount: request.expectedToAmount,
      slippageBps: request.slippageBps,
      executionMode: "executable_calldata_required",
      settlement: {
        deadlineSeconds: Number(process.env.DWF_QUOTE_DEADLINE_SECONDS ?? 60),
        partialFills: true,
        privateExecution: true,
      },
    });
    const timestamp = new Date().toISOString();
    const headers: Record<string, string> = {
      "content-type": "application/json",
      "x-api-key": apiKey,
      "x-request-timestamp": timestamp,
    };
    const signature = signDwf(timestamp, body);
    if (signature) headers["x-request-signature"] = signature;

    const url = process.env.DWF_QUOTE_URL ? new URL(endpoint) : appendQuery(new URL(endpoint.replace(/\/$/, "") + "/quote"), {});
    const response = await fetch(url, {
      method: "POST",
      headers,
      body,
      signal: AbortSignal.timeout(Number(process.env.DWF_QUOTE_TIMEOUT_MS ?? 12_000)),
    });
    const text = await response.text();
    if (!response.ok) throw new Error(`DWF quote endpoint failed with ${response.status}: ${redact(text)}`);
    const payload = asRecord(text ? JSON.parse(text) : {});
    if (!hasExecutableTransaction(payload)) {
      throw new Error("DWF quote response missing executable calldata");
    }
    const outputAmount = stringField(payload, "outputAmount", "buyAmount", "toAmount", "amountOut");
    const quote = buildDexQuote({
      request,
      venue: "dwf",
      liquiditySource: "DWF_LIQUID_MARKETS",
      quoteId: stringField(payload, "quoteId", "id") ?? `dwf:${Date.now()}`,
      outputAmount,
      outputAmountRaw: stringField(payload, "outputAmountRaw", "buyAmountRaw", "toAmountRaw"),
      gasCostUsd: stringField(payload, "gasCostUsd", "estimatedGasUsd") ?? "0",
      failureProbability: Number(process.env.DWF_FAILURE_PROBABILITY ?? 0.08),
      privateSettlement: true,
      expiresAt: stringField(payload, "expiry", "expiresAt") ?? new Date(Date.now() + Number(process.env.DWF_QUOTE_TTL_MS ?? 15_000)).toISOString(),
      metadata: {
        executable: true,
        makerFillGuarantee: true,
        signedExecutableQuote: Boolean(stringField(payload, "signature", "makerSignature")),
        raw: payload,
      },
    });
    return quote;
  }
}

function signDwf(timestamp: string, body: string): string | undefined {
  const secret = process.env.DWF_SIGNING_SECRET;
  if (!secret) return undefined;
  return createHmac("sha256", secret).update(`${timestamp}.${body}`).digest("hex");
}

function redact(text: string): string {
  return text.replace(/[A-Za-z0-9_-]{24,}/g, "<redacted>").slice(0, 500);
}
