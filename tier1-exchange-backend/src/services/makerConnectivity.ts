import { createHmac, randomUUID } from "node:crypto";
import type { QuoteRequest, VenueQuote } from "./venueAdapter.js";
import { SchemaValidRfqSimulator } from "./schemaValidRfqSimulator.js";

export type InstitutionalMakerName = "wintermute" | "cumberland" | "b2c2" | "gsr" | "amber" | "falconx" | "jump" | "otc-hub" | "schema-valid";

export interface InstitutionalMakerEndpoint {
  maker: InstitutionalMakerName;
  endpoint: string;
  apiKeyEnv?: string;
  secretEnv?: string;
  reliability: number;
  maxNotionalUsd: string;
}

export interface MakerConnectivityResult {
  maker: InstitutionalMakerName;
  quote?: VenueQuote;
  unavailableReason?: string;
}

export class MakerConnectivity {
  makers(): InstitutionalMakerEndpoint[] {
    const raw = process.env.INSTITUTIONAL_MAKER_ENDPOINTS_JSON;
    if (!raw) return defaultMakersFromEnv();
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) throw new Error("INSTITUTIONAL_MAKER_ENDPOINTS_JSON must be a JSON array");
    return parsed.map((item) => normalizeMaker(item));
  }

  async requestQuote(maker: InstitutionalMakerEndpoint, request: QuoteRequest): Promise<MakerConnectivityResult> {
    if (!maker.endpoint) return { maker: maker.maker, unavailableReason: "endpoint_not_configured" };
    if (maker.endpoint === "schema-valid://local") {
      return {
        maker: maker.maker,
        quote: await new SchemaValidRfqSimulator().quote(request, `institutional:${maker.maker}`),
      };
    }
    const apiKey = maker.apiKeyEnv ? process.env[maker.apiKeyEnv] : undefined;
    const timestamp = new Date().toISOString();
    const nonce = randomUUID();
    const payload = JSON.stringify({
      ...request,
      executionType: "block-trade-rfq",
      partialFills: true,
      privateSettlement: true,
      requestedAt: timestamp,
      nonce,
    });
    const headers: Record<string, string> = { "content-type": "application/json", "x-rfq-timestamp": timestamp, "x-rfq-nonce": nonce };
    if (apiKey) headers.authorization = `Bearer ${apiKey}`;
    const secret = maker.secretEnv ? process.env[maker.secretEnv] : undefined;
    if (secret) headers["x-rfq-signature"] = createHmac("sha256", secret).update(`${timestamp}.${nonce}.${payload}`).digest("hex");
    const response = await fetch(maker.endpoint, {
      method: "POST",
      headers,
      body: payload,
    });
    if (!response.ok) return { maker: maker.maker, unavailableReason: `http_${response.status}` };
    const body = (await response.json()) as Record<string, unknown>;
    const outputAmount = body.outputAmount ?? body.toAmount ?? body.buyAmount;
    if (!outputAmount) return { maker: maker.maker, unavailableReason: "quote_missing_output_amount" };
    const executable = executableQuoteMetadata(body);
    if (executable.transactionPresent && executable.signatureRequired && !executable.signedResponse) {
      return { maker: maker.maker, unavailableReason: "executable_quote_missing_signature" };
    }
    return {
      maker: maker.maker,
      quote: {
        quoteId: String(body.quoteId ?? `${maker.maker}:${Date.now()}`),
        venue: "rfq",
        liquiditySource: `institutional:${maker.maker}`,
        route: Array.isArray(body.route) ? body.route.map(String) : [request.fromAsset, request.toAsset],
        inputAmount: request.amount,
        outputAmount: String(outputAmount),
        effectivePrice: Number(request.amount) > 0 ? String(Number(outputAmount) / Number(request.amount)) : "0",
        gasCostUsd: String(body.gasCostUsd ?? "0"),
        slippageBps: Number(body.slippageBps ?? "0"),
        liquidityDepth: String(body.liquidityDepth ?? maker.maxNotionalUsd),
        failureProbability: Math.max(0, Math.min(1, 1 - maker.reliability)),
        expiresAt: String(body.expiresAt ?? new Date(Date.now() + 30_000).toISOString()),
        privateSettlement: true,
        metadata: {
          maker: maker.maker,
          blockTrade: true,
          signedRfq: Boolean(secret),
          executable: executable.transactionPresent,
          signedExecutableQuote: executable.transactionPresent && executable.signedResponse,
          makerFillGuarantee: executable.fillGuarantee,
          settlementDeadline: executable.settlementDeadline,
          partialFillSupported: body.partialFillSupported !== false,
          fillableAmount: body.fillableAmount ?? outputAmount,
          privateSettlementChannel: body.privateSettlementChannel ?? "maker-private-channel",
          settlementInstructions: body.settlementInstructions ?? null,
          raw: body,
        },
      },
    };
  }
}

function defaultMakersFromEnv(): InstitutionalMakerEndpoint[] {
  const makers: Array<[InstitutionalMakerName, string, string, string]> = [
    ["wintermute", "WINTERMUTE_RFQ_URL", "WINTERMUTE_API_KEY", "WINTERMUTE_RFQ_SECRET"],
    ["cumberland", "CUMBERLAND_RFQ_URL", "CUMBERLAND_API_KEY", "CUMBERLAND_RFQ_SECRET"],
    ["b2c2", "B2C2_RFQ_URL", "B2C2_API_KEY", "B2C2_RFQ_SECRET"],
    ["gsr", "GSR_RFQ_URL", "GSR_API_KEY", "GSR_RFQ_SECRET"],
    ["amber", "AMBER_RFQ_URL", "AMBER_API_KEY", "AMBER_RFQ_SECRET"],
    ["falconx", "FALCONX_RFQ_URL", "FALCONX_API_KEY", "FALCONX_RFQ_SECRET"],
    ["jump", "JUMP_RFQ_URL", "JUMP_API_KEY", "JUMP_RFQ_SECRET"],
    ["otc-hub", "OTC_HUB_RFQ_URL", "OTC_HUB_API_KEY", "OTC_HUB_RFQ_SECRET"],
  ];
  const configured: InstitutionalMakerEndpoint[] = makers.map(([maker, endpointEnv, apiKeyEnv, secretEnv]) => ({
    maker,
    endpoint: process.env[endpointEnv] ?? "",
    apiKeyEnv,
    secretEnv,
    reliability: Number(process.env[`${maker.toUpperCase().replace(/-/g, "_")}_RELIABILITY`] ?? "0.85"),
    maxNotionalUsd: process.env[`${maker.toUpperCase().replace(/-/g, "_")}_MAX_NOTIONAL_USD`] ?? "0",
  }));
  if (process.env.SCHEMA_VALID_RFQ_SIMULATOR === "1") {
    configured.push({
      maker: "schema-valid",
      endpoint: "schema-valid://local",
      secretEnv: "SCHEMA_VALID_RFQ_SECRET",
      reliability: 0.99,
      maxNotionalUsd: process.env.SCHEMA_VALID_RFQ_MAX_NOTIONAL_USD ?? "0",
    });
  }
  return configured;
}

function normalizeMaker(value: unknown): InstitutionalMakerEndpoint {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid institutional maker endpoint");
  const record = value as Record<string, unknown>;
  return {
    maker: String(record.maker ?? "otc-hub") as InstitutionalMakerName,
    endpoint: String(record.endpoint ?? ""),
    apiKeyEnv: record.apiKeyEnv ? String(record.apiKeyEnv) : undefined,
    secretEnv: record.secretEnv ? String(record.secretEnv) : undefined,
    reliability: Math.max(0, Math.min(1, Number(record.reliability ?? 0.85))),
    maxNotionalUsd: String(record.maxNotionalUsd ?? "0"),
  };
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
  const signedResponse = Boolean(body.signature ?? body.quoteSignature ?? body.makerSignature ?? body.responseSignature);
  return {
    transactionPresent,
    signedResponse,
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
