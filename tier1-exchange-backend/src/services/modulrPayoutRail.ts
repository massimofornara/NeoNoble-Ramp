import { createHmac } from "node:crypto";
import type { BankPayoutDestination } from "./bankPayoutRail.js";

export interface ModulrReadiness {
  ready: boolean;
  provider: "modulr";
  destination: BankPayoutDestination;
  amount: string;
  currency: "EUR";
  reason?: string;
  proof?: Record<string, unknown>;
}

export interface ModulrPayoutInput {
  transactionId: string;
  accountId: string;
  amount: string;
  currency: "EUR";
  settlementId: string;
  txHash: string;
  providerReference?: string;
}

export interface ModulrPayoutResult {
  provider: "modulr";
  transferId: string;
  payoutReference: string;
  status: string;
  destination: BankPayoutDestination;
  proof: Record<string, unknown>;
}

interface ModulrConfig {
  enabled: boolean;
  baseUrl: string;
  paymentUrl: string;
  balanceUrl: string;
  statusUrl: string;
  apiKey: string;
  bearerToken: string;
  signingSecret: string;
  treasuryAccountId: string;
  customerId: string;
  timeoutMs: number;
  confirmationAttempts: number;
  confirmationDelayMs: number;
}

export class ModulrPayoutRail {
  readonly provider = "modulr" as const;

  destination(): BankPayoutDestination {
    return {
      bank: process.env.OFFRAMP_BANK_NAME ?? "UNICREDIT",
      iban: process.env.OFFRAMP_BANK_IBAN ?? "IT22B0200822800000103317304",
      bic: process.env.OFFRAMP_BANK_BIC ?? "UNCRITM1305",
      beneficiary: process.env.OFFRAMP_BANK_BENEFICIARY ?? "Massimo Fornara",
    };
  }

  static configStatus(): Record<string, unknown> {
    const config = modulrConfig();
    return {
      provider: "modulr",
      enabled: config.enabled,
      configured: Boolean(config.enabled && config.paymentUrl && config.balanceUrl && hasAuth(config) && config.treasuryAccountId),
      baseUrlConfigured: Boolean(config.baseUrl),
      paymentUrlConfigured: Boolean(config.paymentUrl),
      balanceUrlConfigured: Boolean(config.balanceUrl),
      statusUrlConfigured: Boolean(config.statusUrl),
      apiKeyConfigured: Boolean(config.apiKey),
      bearerTokenConfigured: Boolean(config.bearerToken),
      signingSecretConfigured: Boolean(config.signingSecret),
      treasuryAccountConfigured: Boolean(config.treasuryAccountId),
      customerConfigured: Boolean(config.customerId),
      confirmationRequired: true,
    };
  }

  async readiness(amount: string): Promise<ModulrReadiness> {
    const destination = this.destination();
    const config = modulrConfig();
    const destinationError = validateDestination(destination);
    if (destinationError) return { ready: false, provider: "modulr", destination, amount, currency: "EUR", reason: destinationError };
    if (process.env.BANK_PAYOUT_EXECUTION_MODE !== "real") {
      return {
        ready: false,
        provider: "modulr",
        destination,
        amount,
        currency: "EUR",
        reason: "BANK_PAYOUT_EXECUTION_MODE must be real before Modulr payout execution",
      };
    }
    if (!config.enabled) {
      return { ready: false, provider: "modulr", destination, amount, currency: "EUR", reason: "MODULR_ENABLED or MODULR_PAYOUTS_ENABLED must be true" };
    }
    if (!config.paymentUrl || !config.balanceUrl || !hasAuth(config) || !config.treasuryAccountId) {
      return {
        ready: false,
        provider: "modulr",
        destination,
        amount,
        currency: "EUR",
        reason: "MODULR_PAYMENT_URL, MODULR_BALANCE_URL, API credentials, and MODULR_ACCOUNT_ID/MODULR_TREASURY_ACCOUNT_ID are required",
      };
    }

    try {
      const balanceProof = await this.fetchBalanceProof(config);
      if (compareDecimal(balanceProof.available, amount) < 0) {
        return {
          ready: false,
          provider: "modulr",
          destination,
          amount,
          currency: "EUR",
          reason: `insufficient Modulr EUR balance: ${balanceProof.available}/${amount}`,
          proof: balanceProof,
        };
      }
      return {
        ready: true,
        provider: "modulr",
        destination,
        amount,
        currency: "EUR",
        proof: balanceProof,
      };
    } catch (error) {
      return {
        ready: false,
        provider: "modulr",
        destination,
        amount,
        currency: "EUR",
        reason: `Modulr readiness check failed: ${error instanceof Error ? error.message : String(error)}`,
      };
    }
  }

  async createPayout(input: ModulrPayoutInput): Promise<ModulrPayoutResult> {
    const readiness = await this.readiness(input.amount);
    if (!readiness.ready) throw new Error(readiness.reason ?? "Modulr rail is not ready");
    const config = modulrConfig();
    const idempotencyKey = `offramp-payout:${input.transactionId}`;
    const body = {
      idempotencyKey,
      externalReference: idempotencyKey,
      sourceAccountId: config.treasuryAccountId,
      customerId: config.customerId || undefined,
      amount: input.amount,
      currency: "EUR",
      paymentType: "SEPA_CREDIT_TRANSFER",
      beneficiary: {
        name: readiness.destination.beneficiary,
        iban: readiness.destination.iban.replace(/\s+/g, ""),
        bic: readiness.destination.bic,
        bankName: readiness.destination.bank,
      },
      remittanceInformation: `NeoNoble ${input.transactionId.slice(0, 18)}`,
      metadata: {
        transactionId: input.transactionId,
        accountId: input.accountId,
        settlementId: input.settlementId,
        txHash: input.txHash,
        providerReference: input.providerReference,
      },
    };

    const submitted = await modulrFetch(config.paymentUrl, config, {
      method: "POST",
      body: JSON.stringify(body),
      idempotencyKey,
    });
    const transferId = extractTransferId(submitted);
    if (!transferId) throw new Error("Modulr payout response missing transfer id/reference");
    const final = await this.requireConfirmedStatus(config, transferId, submitted);
    return {
      provider: "modulr",
      transferId,
      payoutReference: transferId,
      status: final.status,
      destination: readiness.destination,
      proof: {
        type: "modulr.sepa-credit-transfer",
        provider: "modulr",
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

  private async fetchBalanceProof(config = modulrConfig()): Promise<Record<string, unknown> & { available: string }> {
    const body = await modulrFetch(config.balanceUrl, config, { method: "GET" });
    const available =
      stringField(body, "available") ??
      stringField(body, "availableBalance") ??
      stringField(body, "balance") ??
      stringField(asRecord(body).amount, "available") ??
      stringField(asRecord(body).amount, "value") ??
      stringField(asRecord(body).balances, "EUR") ??
      stringField(asRecord(body).balance, "available") ??
      "0";
    return {
      type: "modulr.account-balance",
      provider: "modulr",
      treasuryAccountId: config.treasuryAccountId,
      available,
      currency: "EUR",
      observedAt: new Date().toISOString(),
      raw: body,
    };
  }

  private async requireConfirmedStatus(config: ModulrConfig, transferId: string, submitted: unknown): Promise<{ status: string; payload: unknown }> {
    let payload = submitted;
    let status = normalizeStatus(stringField(payload, "status") ?? stringField(payload, "paymentStatus") ?? "submitted");
    if (isFinalPayoutStatus(status)) return { status, payload };
    if (!config.statusUrl) {
      throw new Error(`Modulr payout submitted but not confirmed by provider yet: ${status}; MODULR_PAYMENT_STATUS_URL is required for confirmation polling`);
    }

    for (let attempt = 0; attempt < config.confirmationAttempts; attempt += 1) {
      if (attempt > 0) await sleep(config.confirmationDelayMs);
      payload = await modulrFetch(statusUrlFor(config.statusUrl, transferId), config, { method: "GET" });
      status = normalizeStatus(stringField(payload, "status") ?? stringField(payload, "paymentStatus") ?? status);
      if (isFinalPayoutStatus(status)) return { status, payload };
      if (isFailedPayoutStatus(status)) throw new Error(`Modulr payout failed with status: ${status}`);
    }
    throw new Error(`Modulr payout not confirmed before timeout: ${status}`);
  }
}

function modulrConfig(): ModulrConfig {
  const baseUrl = stripTrailingSlash(process.env.MODULR_API_URL ?? "");
  const paymentUrl = process.env.MODULR_PAYMENT_URL ?? process.env.MODULR_PAYOUT_URL ?? "";
  const balanceUrl = process.env.MODULR_BALANCE_URL ?? "";
  const statusUrl = process.env.MODULR_PAYMENT_STATUS_URL ?? "";
  return {
    enabled:
      process.env.MODULR_ENABLED === "true" ||
      process.env.MODULR_PAYOUTS_ENABLED === "true" ||
      String(process.env.BANK_RAIL_PROVIDER ?? "").toLowerCase() === "modulr",
    baseUrl,
    paymentUrl: absoluteUrl(paymentUrl, baseUrl),
    balanceUrl: absoluteUrl(balanceUrl, baseUrl),
    statusUrl: absoluteUrl(statusUrl, baseUrl),
    apiKey: process.env.MODULR_API_KEY ?? "",
    bearerToken: process.env.MODULR_ACCESS_TOKEN ?? process.env.MODULR_AUTH_TOKEN ?? "",
    signingSecret: process.env.MODULR_SIGNING_SECRET ?? "",
    treasuryAccountId: process.env.MODULR_ACCOUNT_ID ?? process.env.MODULR_TREASURY_ACCOUNT_ID ?? "",
    customerId: process.env.MODULR_CUSTOMER_ID ?? "",
    timeoutMs: Number(process.env.MODULR_TIMEOUT_MS ?? 30_000),
    confirmationAttempts: Number(process.env.MODULR_CONFIRMATION_ATTEMPTS ?? 6),
    confirmationDelayMs: Number(process.env.MODULR_CONFIRMATION_DELAY_MS ?? 10_000),
  };
}

async function modulrFetch(
  url: string,
  config: ModulrConfig,
  init: RequestInit & { idempotencyKey?: string } = {},
): Promise<unknown> {
  const timestamp = new Date().toISOString();
  const body = typeof init.body === "string" ? init.body : "";
  const signature = config.signingSecret ? createHmac("sha256", config.signingSecret).update(`${timestamp}.${body}`).digest("hex") : undefined;
  const response = await fetch(url, {
    ...init,
    headers: {
      ...(config.bearerToken ? { Authorization: `Bearer ${config.bearerToken}` } : {}),
      ...(config.apiKey ? { "X-API-Key": config.apiKey } : {}),
      "Content-Type": "application/json",
      "Idempotency-Key": init.idempotencyKey ?? "",
      "X-Request-Timestamp": timestamp,
      ...(signature ? { "X-Request-Signature": signature } : {}),
      ...(init.headers ?? {}),
    },
    signal: AbortSignal.timeout(config.timeoutMs),
  });
  const text = await response.text();
  const parsed = text ? (JSON.parse(text) as unknown) : {};
  if (!response.ok) throw new Error(`Modulr ${response.status}: ${safeJson(parsed).slice(0, 500)}`);
  return parsed;
}

function hasAuth(config: ModulrConfig): boolean {
  return Boolean(config.apiKey || config.bearerToken);
}

function validateDestination(destination: BankPayoutDestination): string | undefined {
  if (!/^IT\d{2}[A-Z0-9]{1}\d{10}[A-Z0-9]{12}$/i.test(destination.iban.replace(/\s+/g, ""))) return "Invalid Italian IBAN";
  if (!/^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$/i.test(destination.bic)) return "Invalid BIC/SWIFT";
  if (!destination.beneficiary.trim()) return "Beneficiary is required";
  return undefined;
}

function extractTransferId(value: unknown): string | undefined {
  return (
    stringField(value, "transferId") ??
    stringField(value, "paymentId") ??
    stringField(value, "id") ??
    stringField(value, "payoutReference") ??
    stringField(value, "reference")
  );
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

function stripTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

function absoluteUrl(value: string, baseUrl: string): string {
  if (!value) return "";
  if (/^https?:\/\//i.test(value)) return value;
  if (!baseUrl) return value;
  return `${baseUrl}/${value.replace(/^\/+/, "")}`;
}

function statusUrlFor(template: string, transferId: string): string {
  return template.replace(/\{(transferId|paymentId|id)\}/g, encodeURIComponent(transferId));
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
