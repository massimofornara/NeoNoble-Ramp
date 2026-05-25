import { createHmac, randomUUID, timingSafeEqual } from "node:crypto";
import type { QuoteRequest } from "./venueAdapter.js";
import type {
  ExecutableRfqQuote,
  InstitutionalRfqAdapter,
  InstitutionalRfqProviderName,
  RfqAdapterQuoteResult,
  RfqProviderConfig,
  RfqProviderFailure,
  RfqProviderStatus,
} from "./institutionalRfqTypes.js";

const SIGNATURE_FIELDS = new Set(["signature", "quoteSignature", "makerSignature", "responseSignature"]);

export abstract class BaseInstitutionalRfqAdapter implements InstitutionalRfqAdapter {
  protected constructor(
    readonly provider: InstitutionalRfqProviderName,
    private readonly envPrefix: string,
  ) {}

  status(): RfqProviderStatus {
    const config = this.config(false);
    return {
      provider: this.provider,
      configured: Boolean(config),
      apiUrlConfigured: Boolean(envValue(this.envPrefix, "API_URL") || envValue(this.envPrefix, "RFQ_URL")),
      apiKeyConfigured: Boolean(envValue(this.envPrefix, "API_KEY")),
      signingSecretConfigured: Boolean(envValue(this.envPrefix, "SIGNING_SECRET") || envValue(this.envPrefix, "RFQ_SECRET")),
      executableQuoteSupport: envFlag(`${this.envPrefix}_EXECUTABLE_QUOTE_SUPPORT`, false),
      calldataExecutionMode: envFlag(`${this.envPrefix}_CALLDATA_EXECUTION_MODE`, false),
    };
  }

  async requestQuote(request: QuoteRequest): Promise<RfqAdapterQuoteResult> {
    const config = this.config(false);
    if (!config) {
      return { provider: this.provider, failure: this.failure("not_configured", "provider API_URL/API_KEY/SIGNING_SECRET/executable flags are not fully configured") };
    }
    try {
      const timestamp = new Date().toISOString();
      const nonce = randomUUID();
      const payload = {
        requestId: request.intentId ?? randomUUID(),
        provider: this.provider,
        chainId: request.chainId,
        assetIn: request.fromAsset,
        assetOut: request.toAsset,
        amountIn: request.amount,
        expectedAmountOut: request.expectedToAmount,
        slippageBps: request.slippageBps ?? Number(process.env.RFQ_MAX_SLIPPAGE_BPS ?? 150),
        executableQuoteSupport: true,
        calldataExecutionMode: true,
        partialFills: true,
        settlementDeadline: new Date(Date.now() + Number(process.env.RFQ_SETTLEMENT_DEADLINE_MS ?? 120_000)).toISOString(),
        timestamp,
        nonce,
      };
      const body = JSON.stringify(payload);
      const signature = hmac(config.signingSecret, `${timestamp}.${nonce}.${body}`);
      const response = await fetch(config.apiUrl, {
        method: "POST",
        headers: {
          "content-type": "application/json",
          authorization: `Bearer ${config.apiKey}`,
          "x-rfq-provider": this.provider,
          "x-rfq-timestamp": timestamp,
          "x-rfq-nonce": nonce,
          "x-rfq-signature": signature,
          "idempotency-key": request.intentId ? `${this.provider}:${request.intentId}` : `${this.provider}:${nonce}`,
        },
        body,
      });
      if (!response.ok) {
        return { provider: this.provider, failure: this.failure("http_error", `provider returned HTTP ${response.status}`) };
      }
      const responseBody = (await response.json()) as Record<string, unknown>;
      const quote = this.validateResponse(config, request, responseBody, nonce);
      return { provider: this.provider, quote };
    } catch (error) {
      const rfqFailure = (error as Error & { rfqFailure?: RfqProviderFailure }).rfqFailure;
      if (rfqFailure) return { provider: this.provider, failure: rfqFailure };
      return {
        provider: this.provider,
        failure: this.failure("network_error", error instanceof Error ? error.message : String(error)),
      };
    }
  }

  private config(throwOnMissing: true): RfqProviderConfig;
  private config(throwOnMissing?: false): RfqProviderConfig | undefined;
  private config(throwOnMissing = false): RfqProviderConfig | undefined {
    const apiUrl = envValue(this.envPrefix, "API_URL") ?? envValue(this.envPrefix, "RFQ_URL");
    const apiKey = envValue(this.envPrefix, "API_KEY");
    const signingSecret = envValue(this.envPrefix, "SIGNING_SECRET") ?? envValue(this.envPrefix, "RFQ_SECRET");
    const executableQuoteSupport = envFlag(`${this.envPrefix}_EXECUTABLE_QUOTE_SUPPORT`, false);
    const calldataExecutionMode = envFlag(`${this.envPrefix}_CALLDATA_EXECUTION_MODE`, false);
    const complete = Boolean(apiUrl && apiKey && signingSecret && executableQuoteSupport && calldataExecutionMode);
    if (!complete) {
      if (throwOnMissing) throw new Error(`${this.provider} RFQ provider is not fully configured`);
      return undefined;
    }
    return {
      provider: this.provider,
      apiUrl: String(apiUrl),
      apiKey: String(apiKey),
      signingSecret: String(signingSecret),
      executableQuoteSupport,
      calldataExecutionMode,
      reliability: Number(process.env[`${this.envPrefix}_RELIABILITY`] ?? "0.85"),
      maxNotionalUsd: process.env[`${this.envPrefix}_MAX_NOTIONAL_USD`] ?? "0",
    };
  }

  private validateResponse(config: RfqProviderConfig, request: QuoteRequest, body: Record<string, unknown>, nonce: string): ExecutableRfqQuote {
    const responseNonce = stringField(body, "nonce") ?? stringField(body, "requestNonce") ?? stringField(body, "rfqNonce");
    if (responseNonce && responseNonce !== nonce) throw this.failureError("nonce_mismatch", "provider response nonce does not match RFQ request nonce");
    const quoteId = stringField(body, "quoteId") ?? stringField(body, "id");
    if (!quoteId) throw this.failureError("invalid_response", "quoteId missing");
    const amountOut = stringField(body, "amountOut") ?? stringField(body, "outputAmount") ?? stringField(body, "toAmount") ?? stringField(body, "buyAmount");
    if (!amountOut || Number(amountOut) <= 0) throw this.failureError("no_liquidity", "provider returned no executable output amount");
    const transaction = extractTransaction(body);
    if (!transaction) throw this.failureError("missing_executable_calldata", "provider response has no EVM-compatible transaction calldata");
    const expiry = stringField(body, "expiry") ?? stringField(body, "expiresAt") ?? stringField(body, "expiration") ?? stringField(body, "deadline");
    if (!expiry || Date.parse(expiry) <= Date.now()) throw this.failureError("expired_quote", "provider quote is expired or missing expiry");
    const signature = signatureField(body);
    if (!signature) throw this.failureError("invalid_signature", "provider quote signature missing");
    if (!this.verifyResponseSignature(config.signingSecret, body, signature)) {
      throw this.failureError("invalid_signature", "provider quote signature verification failed");
    }
    const slippageBps = slippage(request.expectedToAmount, amountOut);
    const maxSlippageBps = Number(process.env.RFQ_MAX_SLIPPAGE_BPS ?? request.slippageBps ?? 150);
    if (slippageBps > maxSlippageBps) {
      throw this.failureError("slippage_bounds_exceeded", `slippage ${slippageBps} bps exceeds max ${maxSlippageBps} bps`);
    }
    const partialFillSupported = booleanField(body, "partialFillSupported", true);
    const fillableAmount = stringField(body, "fillableAmount") ?? amountOut;
    if (!partialFillSupported && Number(fillableAmount) < Number(amountOut)) {
      throw this.failureError("liquidity_unavailable", "provider fillable amount is below quoted amount and partial fills are disabled");
    }
    const settlementDeadline = stringField(body, "settlementDeadline") ?? expiry;
    const responseTimestamp = stringField(body, "timestamp") ?? stringField(body, "responseTimestamp") ?? stringField(body, "signedAt");
    if (responseTimestamp) {
      const skewMs = Math.abs(Date.now() - Date.parse(responseTimestamp));
      if (Number.isFinite(skewMs) && skewMs > Number(process.env.RFQ_MAX_RESPONSE_SKEW_MS ?? 120_000)) {
        throw this.failureError("invalid_response", "provider response timestamp is outside accepted skew");
      }
    }
    return {
      provider: this.provider,
      quoteId,
      assetIn: stringField(body, "assetIn") ?? stringField(body, "fromAsset") ?? request.fromAsset,
      assetOut: stringField(body, "assetOut") ?? stringField(body, "toAsset") ?? request.toAsset,
      amountIn: stringField(body, "amountIn") ?? stringField(body, "inputAmount") ?? request.amount,
      amountOut,
      calldata: transaction.data,
      expiry,
      signature,
      executable: true,
      transaction,
      route: Array.isArray(body.route) ? body.route.map(String) : [request.fromAsset, request.toAsset],
      gasCostUsd: stringField(body, "gasCostUsd") ?? "0",
      slippageBps,
      liquidityDepth: stringField(body, "liquidityDepth") ?? fillableAmount,
      failureProbability: Math.max(0, Math.min(1, 1 - config.reliability)),
      partialFillSupported,
      fillableAmount,
      makerFillGuarantee: booleanField(body, "makerFillGuarantee", booleanField(body, "fillGuarantee", false)),
      settlementDeadline,
      privateSettlementChannel: stringField(body, "privateSettlementChannel"),
      requestNonce: nonce,
      responseTimestamp,
      raw: body,
    };
  }

  private verifyResponseSignature(secret: string, body: Record<string, unknown>, signature: string): boolean {
    const payload = canonicalJson(stripSignatureFields(body));
    const expected = hmac(secret, payload);
    return safeEqualHex(expected, signature);
  }

  private failure(reason: RfqProviderFailure["reason"], detail: string): RfqProviderFailure {
    return { provider: this.provider, reason, detail };
  }

  private failureError(reason: RfqProviderFailure["reason"], detail: string): Error {
    const error = new Error(`${reason}: ${detail}`);
    (error as Error & { rfqFailure?: RfqProviderFailure }).rfqFailure = this.failure(reason, detail);
    return error;
  }
}

function envValue(prefix: string, suffix: string): string | undefined {
  const value = process.env[`${prefix}_${suffix}`];
  return value && value.trim() ? value.trim() : undefined;
}

function envFlag(key: string, fallback: boolean): boolean {
  const value = process.env[key];
  if (value === undefined) return fallback;
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function hmac(secret: string, payload: string): string {
  return createHmac("sha256", secret).update(payload).digest("hex");
}

function safeEqualHex(left: string, right: string): boolean {
  const cleanRight = right.startsWith("0x") ? right.slice(2) : right;
  if (!/^[a-fA-F0-9]+$/.test(cleanRight)) return false;
  const leftBuffer = Buffer.from(left, "hex");
  const rightBuffer = Buffer.from(cleanRight, "hex");
  return leftBuffer.length === rightBuffer.length && timingSafeEqual(leftBuffer, rightBuffer);
}

function extractTransaction(body: Record<string, unknown>): ExecutableRfqQuote["transaction"] | undefined {
  const transaction = firstRecord(body.transaction, body.tx, body.settlementTransaction, asRecord(body.execution).transaction, asRecord(body.execution).tx);
  if (!transaction) return undefined;
  const to = stringField(transaction, "to") ?? stringField(transaction, "target");
  const data = stringField(transaction, "data") ?? stringField(transaction, "calldata");
  if (!to || !/^0x[a-fA-F0-9]{40}$/.test(to)) return undefined;
  if (!data || !/^0x([a-fA-F0-9]{2})*$/.test(data)) return undefined;
  return {
    to,
    data,
    valueWei: stringField(transaction, "valueWei") ?? stringField(transaction, "value") ?? "0",
    gasLimit: stringField(transaction, "gasLimit"),
  };
}

function slippage(expected: string | undefined, output: string): number {
  const expectedValue = Number(expected ?? output);
  const outputValue = Number(output);
  if (!Number.isFinite(expectedValue) || expectedValue <= 0 || !Number.isFinite(outputValue)) return 0;
  return Math.max(0, Math.round(((expectedValue - outputValue) / expectedValue) * 10_000));
}

function signatureField(body: Record<string, unknown>): string | undefined {
  return stringField(body, "signature") ?? stringField(body, "quoteSignature") ?? stringField(body, "makerSignature") ?? stringField(body, "responseSignature");
}

function stripSignatureFields(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stripSignatureFields);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .filter(([key]) => !SIGNATURE_FIELDS.has(key))
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, field]) => [key, stripSignatureFields(field)]),
  );
}

function canonicalJson(value: unknown): string {
  return JSON.stringify(value);
}

function stringField(value: Record<string, unknown>, key: string): string | undefined {
  const field = value[key];
  return field === undefined || field === null ? undefined : String(field);
}

function booleanField(value: Record<string, unknown>, key: string, fallback: boolean): boolean {
  const field = value[key];
  if (field === undefined || field === null) return fallback;
  if (typeof field === "boolean") return field;
  return ["1", "true", "yes", "on"].includes(String(field).toLowerCase());
}

function firstRecord(...values: unknown[]): Record<string, unknown> | undefined {
  return values.find((value): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value));
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}
