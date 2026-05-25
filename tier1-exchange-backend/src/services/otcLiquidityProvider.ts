import { createHmac, randomUUID } from "node:crypto";
import type { QuoteRequest, VenueQuote } from "./venueAdapter.js";
import type { MakerProfile } from "./makerQuoteBook.js";
import { SchemaValidRfqSimulator } from "./schemaValidRfqSimulator.js";

export class OtcLiquidityProvider {
  async requestQuote(maker: MakerProfile, request: QuoteRequest): Promise<VenueQuote | undefined> {
    if (maker.endpoint === "schema-valid://local") {
      return new SchemaValidRfqSimulator().quote(request, `rfq:${maker.makerId}`);
    }
    const timestamp = new Date().toISOString();
    const nonce = randomUUID();
    const payload = JSON.stringify({
      ...request,
      settlement: "private",
      partialFills: true,
      requestedAt: timestamp,
      nonce,
    });
    const headers: Record<string, string> = { "content-type": "application/json", "x-rfq-timestamp": timestamp, "x-rfq-nonce": nonce };
    if (maker.apiKeyEnv && process.env[maker.apiKeyEnv]) headers.authorization = `Bearer ${process.env[maker.apiKeyEnv]}`;
    const secret = maker.secretEnv ? process.env[maker.secretEnv] : undefined;
    if (secret) headers["x-rfq-signature"] = createHmac("sha256", secret).update(`${timestamp}.${nonce}.${payload}`).digest("hex");
    const response = await fetch(maker.endpoint, {
      method: "POST",
      headers,
      body: payload,
    });
    if (!response.ok) {
      throw new Error(`RFQ maker ${maker.makerId} failed with ${response.status}`);
    }
    const body = (await response.json()) as Record<string, unknown>;
    const outputAmount = body.outputAmount ?? body.toAmount ?? body.buyAmount;
    if (!outputAmount) return undefined;
    const executable = executableQuoteMetadata(body);
    if (executable.transactionPresent && executable.signatureRequired && !executable.signedResponse) {
      throw new Error(`RFQ maker ${maker.makerId} returned executable calldata without a maker signature`);
    }
    return {
      quoteId: String(body.quoteId ?? `rfq:${maker.makerId}:${Date.now()}`),
      venue: "rfq",
      liquiditySource: `rfq:${maker.makerId}`,
      route: Array.isArray(body.route) ? body.route.map(String) : [request.fromAsset, request.toAsset],
      inputAmount: request.amount,
      outputAmount: String(outputAmount),
      effectivePrice: Number(request.amount) > 0 ? String(Number(outputAmount) / Number(request.amount)) : "0",
      gasCostUsd: String(body.gasCostUsd ?? "0"),
      slippageBps: Number(body.slippageBps ?? "0"),
      liquidityDepth: String(body.liquidityDepth ?? outputAmount),
      failureProbability: Math.max(0, Math.min(1, 1 - maker.reliability)),
      expiresAt: String(body.expiresAt ?? new Date(Date.now() + 30_000).toISOString()),
      privateSettlement: maker.privateSettlement,
      metadata: {
        makerId: maker.makerId,
        makerReliability: maker.reliability,
        signedRfq: Boolean(secret),
        executable: executable.transactionPresent,
        signedExecutableQuote: executable.transactionPresent && executable.signedResponse,
        makerFillGuarantee: executable.fillGuarantee,
        settlementDeadline: executable.settlementDeadline,
        partialFillSupported: body.partialFillSupported !== false,
        fillableAmount: body.fillableAmount ?? outputAmount,
        privateSettlementChannel: body.privateSettlementChannel ?? "otc-private-channel",
        raw: body,
      },
    };
  }
}

function executableQuoteMetadata(body: Record<string, unknown>): {
  transactionPresent: boolean;
  signedResponse: boolean;
  signatureRequired: boolean;
  fillGuarantee: boolean;
  settlementDeadline: string | undefined;
} {
  const transaction = firstRecord(
    body.transaction,
    body.tx,
    body.settlementTransaction,
    asRecord(body.execution).transaction,
    asRecord(body.execution).tx,
  );
  const transactionPresent = Boolean(
    transaction &&
      /^0x[a-fA-F0-9]{40}$/.test(String(transaction.to ?? transaction.target ?? "")) &&
      /^0x([a-fA-F0-9]{2})*$/.test(String(transaction.data ?? transaction.calldata ?? "")),
  );
  return {
    transactionPresent,
    signedResponse: Boolean(body.signature ?? body.quoteSignature ?? body.makerSignature ?? body.responseSignature),
    signatureRequired: process.env.RFQ_REQUIRE_SIGNED_EXECUTABLE_QUOTES !== "0",
    fillGuarantee: Boolean(body.fillGuarantee ?? body.makerFillGuarantee ?? body.guaranteed ?? false),
    settlementDeadline: body.settlementDeadline || body.deadline || body.expiresAt ? String(body.settlementDeadline ?? body.deadline ?? body.expiresAt) : undefined,
  };
}

function firstRecord(...values: unknown[]): Record<string, unknown> | undefined {
  return values.find((value): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value));
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}
