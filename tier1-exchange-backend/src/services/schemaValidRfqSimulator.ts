import { createHmac, createHash, randomUUID } from "node:crypto";
import type { QuoteRequest, VenueQuote } from "./venueAdapter.js";
import { ValuationService } from "./valuationService.js";

export class SchemaValidRfqSimulator {
  async quote(request: QuoteRequest, source = "schema-valid-rfq-simulator"): Promise<VenueQuote> {
    const valuation = await new ValuationService().swapNenoToAsset(request.amount, request.toAsset);
    const outputAmount = request.expectedToAmount ?? valuation.targetAmount;
    const expiresAt = new Date(Date.now() + Number(process.env.SCHEMA_VALID_RFQ_TTL_MS ?? 30_000)).toISOString();
    const quoteId = `schema-rfq:${randomUUID()}`;
    const payload = {
      quoteId,
      request,
      outputAmount,
      expiresAt,
      source,
      settlementMode: "quote-only-no-settlement-proof",
    };
    const secret = process.env.SCHEMA_VALID_RFQ_SECRET ?? "schema-valid-rfq-local-secret";
    const signature = createHmac("sha256", secret).update(JSON.stringify(payload)).digest("hex");
    return {
      quoteId,
      venue: "rfq",
      liquiditySource: source,
      route: [request.fromAsset.toUpperCase(), request.toAsset.toUpperCase()],
      inputAmount: request.amount,
      outputAmount,
      effectivePrice: Number(request.amount) > 0 ? String(Number(outputAmount) / Number(request.amount)) : "0",
      gasCostUsd: "0",
      slippageBps: 0,
      liquidityDepth: process.env.SCHEMA_VALID_RFQ_LIQUIDITY_DEPTH ?? outputAmount,
      failureProbability: Number(process.env.SCHEMA_VALID_RFQ_FAILURE_PROBABILITY ?? "0.01"),
      expiresAt,
      privateSettlement: true,
      metadata: {
        schemaValidSimulator: true,
        signedResponse: true,
        quoteSignature: signature,
        quoteDigest: createHash("sha256").update(JSON.stringify(payload)).digest("hex"),
        partialFillSupported: true,
        privateSettlementChannel: "schema-valid-rfq-channel",
        settlementInstructions: null,
        executionCaveat: "This quote is schema-valid for routing/failover tests and never creates txHash or settlement proof.",
        raw: payload,
      },
    };
  }
}
