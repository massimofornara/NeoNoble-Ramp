import { createHmac } from "node:crypto";
import type { BankPayoutDestination } from "./bankPayoutRail.js";

export interface DirectSepaReadiness {
  ready: boolean;
  provider: string;
  destination: BankPayoutDestination;
  amount: string;
  currency: "EUR";
  reason?: string;
  proof?: Record<string, unknown>;
}

export interface DirectSepaPayoutInput {
  transactionId: string;
  accountId: string;
  amount: string;
  currency: "EUR";
  settlementId: string;
  txHash: string;
  providerReference?: string;
}

export interface DirectSepaPayoutResult {
  provider: string;
  transferId: string;
  payoutReference: string;
  status: string;
  destination: BankPayoutDestination;
  proof: Record<string, unknown>;
}

export class DirectSepaPayoutRail {
  static configStatus(): Record<string, unknown> {
    const config = railConfig();
    return {
      provider: config.provider,
      enabled: config.enabled,
      configured: Boolean(config.enabled && config.submitUrl && config.balanceUrl && config.statusUrl && config.apiKey && config.treasuryAccountId),
      submitUrlConfigured: Boolean(config.submitUrl),
      balanceUrlConfigured: Boolean(config.balanceUrl),
      statusUrlConfigured: Boolean(config.statusUrl),
      apiKeyConfigured: Boolean(config.apiKey),
      signingSecretConfigured: Boolean(config.signingSecret),
      treasuryAccountConfigured: Boolean(config.treasuryAccountId),
      confirmationRequired: true,
    };
  }

  destination(): BankPayoutDestination {
    return {
      bank: process.env.OFFRAMP_BANK_NAME ?? "UNICREDIT",
      iban: process.env.OFFRAMP_BANK_IBAN ?? "IT22B0200822800000103317304",
      bic: process.env.OFFRAMP_BANK_BIC ?? "UNCRITM1305",
      beneficiary: process.env.OFFRAMP_BANK_BENEFICIARY ?? "Massimo Fornara",
    };
  }

  async readiness(amount: string): Promise<DirectSepaReadiness> {
    const destination = this.destination();
    const config = railConfig();
    const destinationError = validateDestination(destination);
    if (destinationError) return { ready: false, provider: config.provider, destination, amount, currency: "EUR", reason: destinationError };
    if (process.env.BANK_PAYOUT_EXECUTION_MODE !== "real") {
      return {
        ready: false,
        provider: config.provider,
        destination,
        amount,
        currency: "EUR",
        reason: "BANK_PAYOUT_EXECUTION_MODE must be real before direct SEPA payout execution",
      };
    }
    if (!config.enabled) {
      return { ready: false, provider: config.provider, destination, amount, currency: "EUR", reason: "BANK_RAIL_ENABLED or SEPA_RAIL_ENABLED must be true" };
    }
    if (!config.submitUrl || !config.apiKey || !config.treasuryAccountId) {
      return {
        ready: false,
        provider: config.provider,
        destination,
        amount,
        currency: "EUR",
        reason: "BANK_RAIL_SUBMIT_URL/SEPA_PAYOUT_API_URL, API key, and treasury account id are required",
      };
    }
    if (!config.statusUrl) {
      return {
        ready: false,
        provider: config.provider,
        destination,
        amount,
        currency: "EUR",
        reason: "BANK_RAIL_STATUS_URL or SEPA_PAYOUT_STATUS_URL is required for direct SEPA payout finality",
      };
    }
    if (!config.balanceUrl) {
      return {
        ready: false,
        provider: config.provider,
        destination,
        amount,
        currency: "EUR",
        reason: "BANK_RAIL_BALANCE_URL or SEPA_BALANCE_API_URL is required for treasury EUR liquidity proof",
      };
    }

    try {
      const balanceProof = await this.fetchBalanceProof(config);
      if (compareDecimal(balanceProof.available, amount) < 0) {
        return {
          ready: false,
          provider: config.provider,
          destination,
          amount,
          currency: "EUR",
          reason: `insufficient ${config.provider} EUR balance: ${balanceProof.available}/${amount}`,
          proof: balanceProof,
        };
      }
      return {
        ready: true,
        provider: config.provider,
        destination,
        amount,
        currency: "EUR",
        proof: balanceProof,
      };
    } catch (error) {
      return {
        ready: false,
        provider: config.provider,
        destination,
        amount,
        currency: "EUR",
        reason: `direct SEPA readiness check failed: ${error instanceof Error ? error.message : String(error)}`,
      };
    }
  }

  async createPayout(input: DirectSepaPayoutInput): Promise<DirectSepaPayoutResult> {
    const readiness = await this.readiness(input.amount);
    if (!readiness.ready) throw new Error(readiness.reason ?? "direct SEPA rail is not ready");
    const config = railConfig();
    const idempotencyKey = `offramp-payout:${input.transactionId}`;
    const body = {
      idempotencyKey,
      treasuryAccountId: config.treasuryAccountId,
      amount: input.amount,
      currency: "EUR",
      rail: "SEPA_CREDIT_TRANSFER",
      destination: readiness.destination,
      remittanceReference: `NeoNoble ${input.transactionId.slice(0, 18)}`,
      metadata: {
        transactionId: input.transactionId,
        accountId: input.accountId,
        settlementId: input.settlementId,
        txHash: input.txHash,
        providerReference: input.providerReference,
      },
    };
    const submitted = await providerFetch(config.submitUrl, config, {
      method: "POST",
      body: JSON.stringify(body),
      idempotencyKey,
    });
    const transferId = stringField(submitted, "transferId") ?? stringField(submitted, "id") ?? stringField(submitted, "payoutReference");
    if (!transferId) throw new Error(`${config.provider} payout response missing transfer id/reference`);
    const final = await requireConfirmedStatus(config, transferId, submitted);
    return {
      provider: config.provider,
      transferId,
      payoutReference: transferId,
      status: final.status,
      destination: readiness.destination,
      proof: {
        type: "direct-sepa-bank-transfer",
        provider: config.provider,
        transferId,
        status: final.status,
        treasuryAccountId: config.treasuryAccountId,
        settlementId: input.settlementId,
        txHash: input.txHash,
        providerReference: input.providerReference,
        observedAt: new Date().toISOString(),
        submitted,
        confirmed: final.payload,
      },
    };
  }

  private async fetchBalanceProof(config = railConfig()): Promise<Record<string, unknown> & { available: string }> {
    const body = await providerFetch(config.balanceUrl, config, { method: "GET" });
    const available =
      stringField(body, "available") ??
      stringField(body, "availableBalance") ??
      stringField(asRecord(body).balance, "available") ??
      stringField(asRecord(body).balances, "EUR") ??
      "0";
    return {
      type: "direct-sepa-treasury-balance",
      provider: config.provider,
      treasuryAccountId: config.treasuryAccountId,
      available,
      currency: "EUR",
      observedAt: new Date().toISOString(),
      raw: body,
    };
  }
}

function railConfig(): {
  provider: string;
  enabled: boolean;
  submitUrl: string;
  balanceUrl: string;
  statusUrl: string;
  apiKey: string;
  signingSecret: string;
  treasuryAccountId: string;
  confirmationAttempts: number;
  confirmationDelayMs: number;
} {
  return {
    provider: process.env.BANK_RAIL_PROVIDER ?? process.env.SEPA_PROVIDER_NAME ?? "direct-sepa",
    enabled: process.env.BANK_RAIL_ENABLED === "true" || process.env.SEPA_RAIL_ENABLED === "true",
    submitUrl: process.env.BANK_RAIL_SUBMIT_URL ?? process.env.SEPA_PAYOUT_API_URL ?? "",
    balanceUrl: process.env.BANK_RAIL_BALANCE_URL ?? process.env.SEPA_BALANCE_API_URL ?? "",
    statusUrl: process.env.BANK_RAIL_STATUS_URL ?? process.env.SEPA_PAYOUT_STATUS_URL ?? "",
    apiKey: process.env.BANK_RAIL_API_KEY ?? process.env.SEPA_PROVIDER_API_KEY ?? "",
    signingSecret: process.env.BANK_RAIL_SIGNING_SECRET ?? process.env.SEPA_PROVIDER_SIGNING_SECRET ?? "",
    treasuryAccountId: process.env.BANK_RAIL_TREASURY_ACCOUNT_ID ?? process.env.SEPA_TREASURY_ACCOUNT_ID ?? "",
    confirmationAttempts: Number(process.env.BANK_RAIL_CONFIRMATION_ATTEMPTS ?? 6),
    confirmationDelayMs: Number(process.env.BANK_RAIL_CONFIRMATION_DELAY_MS ?? 10_000),
  };
}

async function requireConfirmedStatus(
  config: ReturnType<typeof railConfig>,
  transferId: string,
  submitted: unknown,
): Promise<{ status: string; payload: unknown }> {
  let payload = submitted;
  let status = normalizeStatus(stringField(payload, "status") ?? stringField(payload, "paymentStatus") ?? "submitted");
  if (isFinalPayoutStatus(status)) return { status, payload };
  if (isFailedPayoutStatus(status)) throw new Error(`${config.provider} payout failed with status: ${status}`);

  for (let attempt = 0; attempt < config.confirmationAttempts; attempt += 1) {
    if (attempt > 0) await sleep(config.confirmationDelayMs);
    payload = await providerFetch(statusUrlFor(config.statusUrl, transferId), config, { method: "GET" });
    status = normalizeStatus(stringField(payload, "status") ?? stringField(payload, "paymentStatus") ?? status);
    if (isFinalPayoutStatus(status)) return { status, payload };
    if (isFailedPayoutStatus(status)) throw new Error(`${config.provider} payout failed with status: ${status}`);
  }
  throw new Error(`${config.provider} payout not confirmed before timeout: ${status}`);
}

async function providerFetch(
  url: string,
  config: ReturnType<typeof railConfig>,
  init: RequestInit & { idempotencyKey?: string } = {},
): Promise<unknown> {
  const timestamp = new Date().toISOString();
  const body = typeof init.body === "string" ? init.body : "";
  const signature = config.signingSecret ? createHmac("sha256", config.signingSecret).update(`${timestamp}.${body}`).digest("hex") : undefined;
  const response = await fetch(url, {
    ...init,
    headers: {
      Authorization: `Bearer ${config.apiKey}`,
      "Content-Type": "application/json",
      "Idempotency-Key": init.idempotencyKey ?? "",
      "X-Request-Timestamp": timestamp,
      ...(signature ? { "X-Request-Signature": signature } : {}),
      ...(init.headers ?? {}),
    },
    signal: AbortSignal.timeout(Number(process.env.BANK_RAIL_TIMEOUT_MS ?? 30_000)),
  });
  const text = await response.text();
  const parsed = text ? (JSON.parse(text) as unknown) : {};
  if (!response.ok) throw new Error(`${config.provider} ${response.status}: ${safeJson(parsed).slice(0, 500)}`);
  return parsed;
}

function validateDestination(destination: BankPayoutDestination): string | undefined {
  if (!/^IT\d{2}[A-Z0-9]{1}\d{10}[A-Z0-9]{12}$/i.test(destination.iban.replace(/\s+/g, ""))) return "Invalid Italian IBAN";
  if (!/^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$/i.test(destination.bic)) return "Invalid BIC/SWIFT";
  if (!destination.beneficiary.trim()) return "Beneficiary is required";
  return undefined;
}

function compareDecimal(left: string, right: string): number {
  const leftUnits = decimalToCents(left);
  const rightUnits = decimalToCents(right);
  return leftUnits === rightUnits ? 0 : leftUnits > rightUnits ? 1 : -1;
}

function decimalToCents(value: string): bigint {
  const normalized = String(value ?? "0").trim();
  if (!/^\d+(\.\d+)?$/.test(normalized)) return 0n;
  const [whole, fraction = ""] = normalized.split(".");
  return BigInt(`${whole}${fraction.padEnd(2, "0").slice(0, 2)}`);
}

function stringField(value: unknown, field: string): string | undefined {
  const fieldValue = asRecord(value)[field];
  return fieldValue === undefined || fieldValue === null ? undefined : String(fieldValue);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function isFinalPayoutStatus(status: string): boolean {
  return ["confirmed", "completed", "executed", "settled", "paid"].includes(status);
}

function isFailedPayoutStatus(status: string): boolean {
  return ["failed", "rejected", "cancelled", "returned"].includes(status);
}

function normalizeStatus(status: string): string {
  return String(status).trim().toLowerCase();
}

function statusUrlFor(template: string, transferId: string): string {
  return template.replace(/\{(transferId|paymentId|id)\}/g, encodeURIComponent(transferId));
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
