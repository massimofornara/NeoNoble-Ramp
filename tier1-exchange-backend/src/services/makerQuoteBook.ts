export interface MakerProfile {
  makerId: string;
  endpoint: string;
  apiKeyEnv?: string;
  secretEnv?: string;
  reliability: number;
  maxNotional: string;
  privateSettlement: boolean;
}

export class MakerQuoteBook {
  makers(): MakerProfile[] {
    const raw = process.env.RFQ_MAKER_ENDPOINTS_JSON;
    if (!raw) {
      return process.env.SCHEMA_VALID_RFQ_SIMULATOR === "1"
        ? [
            {
              makerId: "schema-valid",
              endpoint: "schema-valid://local",
              secretEnv: "SCHEMA_VALID_RFQ_SECRET",
              reliability: 0.99,
              maxNotional: process.env.SCHEMA_VALID_RFQ_MAX_NOTIONAL_USD ?? "0",
              privateSettlement: true,
            },
          ]
        : [];
    }
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) throw new Error("RFQ_MAKER_ENDPOINTS_JSON must be a JSON array");
    return parsed.map((item) => makerFrom(item));
  }
}

function makerFrom(value: unknown): MakerProfile {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Invalid RFQ maker profile");
  }
  const record = value as Record<string, unknown>;
  const endpoint = String(record.endpoint ?? "");
  if (!/^https?:\/\//.test(endpoint) && endpoint !== "schema-valid://local") throw new Error("RFQ maker endpoint must be http(s)");
  return {
    makerId: String(record.makerId ?? endpoint),
    endpoint,
    apiKeyEnv: record.apiKeyEnv ? String(record.apiKeyEnv) : undefined,
    secretEnv: record.secretEnv ? String(record.secretEnv) : undefined,
    reliability: Math.max(0, Math.min(1, Number(record.reliability ?? 0.8))),
    maxNotional: String(record.maxNotional ?? "0"),
    privateSettlement: record.privateSettlement !== false,
  };
}
