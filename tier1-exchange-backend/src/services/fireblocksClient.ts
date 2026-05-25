import { createHash, createSign, randomUUID } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";

export interface FireblocksClientConfig {
  apiKey: string;
  privateKeyPath: string;
  baseUrl: string;
  vaultAccountId: string;
  webhookSecret?: string;
  nenoAssetId?: string;
  stablecoinAssetId?: string;
}

export interface FireblocksReadiness {
  configured: boolean;
  missing: string[];
  baseUrl?: string;
  vaultAccountId?: string;
  nenoAssetId?: string;
  stablecoinAssetId?: string;
  sandbox: boolean;
}

export class FireblocksClient {
  private readonly privateKey: string;

  constructor(readonly config: FireblocksClientConfig) {
    if (!existsSync(config.privateKeyPath)) {
      throw new Error("FIREBLOCKS_PRIVATE_KEY_PATH does not point to a readable private key file");
    }
    this.privateKey = readFileSync(config.privateKeyPath, "utf8");
  }

  static readinessFromEnv(): FireblocksReadiness {
    const missing = requiredEnv()
      .filter((key) => !process.env[key])
      .concat(process.env.FIREBLOCKS_PRIVATE_KEY_PATH && !existsSync(process.env.FIREBLOCKS_PRIVATE_KEY_PATH) ? ["FIREBLOCKS_PRIVATE_KEY_PATH(readable)"] : []);
    return {
      configured: missing.length === 0,
      missing,
      baseUrl: process.env.FIREBLOCKS_BASE_URL,
      vaultAccountId: process.env.FIREBLOCKS_VAULT_ACCOUNT_ID,
      nenoAssetId: process.env.FIREBLOCKS_NENO_ASSET_ID,
      stablecoinAssetId: process.env.FIREBLOCKS_STABLECOIN_ASSET_ID,
      sandbox: /sandbox/i.test(process.env.FIREBLOCKS_BASE_URL ?? ""),
    };
  }

  static fromEnv(): FireblocksClient {
    const readiness = FireblocksClient.readinessFromEnv();
    if (!readiness.configured) {
      throw new Error(`Fireblocks is not configured: missing ${readiness.missing.join(", ")}`);
    }
    return new FireblocksClient({
      apiKey: process.env.FIREBLOCKS_API_KEY ?? "",
      privateKeyPath: process.env.FIREBLOCKS_PRIVATE_KEY_PATH ?? "",
      baseUrl: (process.env.FIREBLOCKS_BASE_URL ?? "").replace(/\/+$/, ""),
      vaultAccountId: process.env.FIREBLOCKS_VAULT_ACCOUNT_ID ?? "",
      webhookSecret: process.env.FIREBLOCKS_WEBHOOK_SECRET,
      nenoAssetId: process.env.FIREBLOCKS_NENO_ASSET_ID,
      stablecoinAssetId: process.env.FIREBLOCKS_STABLECOIN_ASSET_ID,
    });
  }

  async getVaultAccount(vaultAccountId = this.config.vaultAccountId): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>("GET", `/v1/vault/accounts/${encodeURIComponent(vaultAccountId)}`);
  }

  async getVaultAssetBalance(vaultAccountId: string, assetId: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(
      "GET",
      `/v1/vault/accounts/${encodeURIComponent(vaultAccountId)}/${encodeURIComponent(assetId)}`,
    );
  }

  async createTransaction(body: FireblocksCreateTransactionRequest): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>("POST", "/v1/transactions", body);
  }

  async getTransactionById(txId: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>("GET", `/v1/transactions/${encodeURIComponent(txId)}`);
  }

  async createPayout(body: FireblocksCreatePayoutRequest, idempotencyKey: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>("POST", "/v1/payments/payout", body, idempotencyKey);
  }

  async executePayout(payoutId: string, idempotencyKey: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>("POST", `/v1/payments/payout/${encodeURIComponent(payoutId)}/actions/execute`, {}, idempotencyKey);
  }

  async getPayout(payoutId: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>("GET", `/v1/payments/payout/${encodeURIComponent(payoutId)}`);
  }

  private async request<T>(method: "GET" | "POST", path: string, body?: unknown, idempotencyKey?: string): Promise<T> {
    const rawBody = body === undefined ? "" : JSON.stringify(body);
    const token = this.jwt(path, rawBody);
    const response = await fetch(`${this.config.baseUrl}${path}`, {
      method,
      headers: {
        "content-type": "application/json",
        "x-api-key": this.config.apiKey,
        authorization: `Bearer ${token}`,
        ...(idempotencyKey ? { "idempotency-key": idempotencyKey } : {}),
      },
      body: method === "GET" ? undefined : rawBody,
    });
    const text = await response.text();
    const parsed = text ? (JSON.parse(text) as unknown) : {};
    if (!response.ok) {
      const statusHint = response.status === 401 ? "Fireblocks authentication failed; verify JWT private key, API key, base URL, and clock skew" : "Fireblocks request failed";
      throw new Error(`${statusHint}: ${response.status} ${redactedFireblocksError(parsed)}`);
    }
    return parsed as T;
  }

  private jwt(uri: string, rawBody: string): string {
    const now = Math.floor(Date.now() / 1000);
    const header = base64UrlJson({ alg: "RS256", typ: "JWT" });
    const payload = base64UrlJson({
      uri,
      nonce: randomUUID(),
      iat: now,
      exp: now + 25,
      sub: this.config.apiKey,
      bodyHash: createHash("sha256").update(rawBody).digest("hex"),
    });
    const signer = createSign("RSA-SHA256");
    signer.update(`${header}.${payload}`);
    signer.end();
    const signature = signer.sign(this.privateKey, "base64url");
    return `${header}.${payload}.${signature}`;
  }
}

export interface FireblocksCreateTransactionRequest {
  assetId: string;
  amount: string;
  source: {
    type: "VAULT_ACCOUNT";
    id: string;
  };
  destination: {
    type: "ONE_TIME_ADDRESS";
    oneTimeAddress: {
      address: string;
      tag?: string;
    };
  };
  note?: string;
  externalTxId?: string;
  feeLevel?: "LOW" | "MEDIUM" | "HIGH";
}

export interface FireblocksCreatePayoutRequest {
  paymentAccount: {
    id: string;
    type: "VAULT_ACCOUNT" | "EXCHANGE_ACCOUNT" | "FIAT_ACCOUNT";
  };
  instructionSet: Array<{
    name: string;
    payeeAccount: {
      id: string;
      type: "VAULT_ACCOUNT" | "EXCHANGE_ACCOUNT" | "FIAT_ACCOUNT" | "EXTERNAL_WALLET" | "NETWORK_CONNECTION" | "MERCHANT_ACCOUNT";
    };
    amount: {
      amount: string;
      assetId: string;
    };
  }>;
}

function requiredEnv(): string[] {
  return ["FIREBLOCKS_API_KEY", "FIREBLOCKS_PRIVATE_KEY_PATH", "FIREBLOCKS_BASE_URL", "FIREBLOCKS_VAULT_ACCOUNT_ID"];
}

function base64UrlJson(value: Record<string, unknown>): string {
  return Buffer.from(JSON.stringify(value)).toString("base64url");
}

function redactedFireblocksError(value: unknown): string {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.replace(/[A-Za-z0-9_-]{24,}/g, "[redacted]");
}
