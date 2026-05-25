export interface BankPayoutDestination {
  bank: string;
  iban: string;
  bic: string;
  beneficiary: string;
}

export interface BankPayoutReadiness {
  ready: boolean;
  provider?: "wise";
  destination: BankPayoutDestination;
  amount: string;
  currency: "EUR";
  reason?: string;
  proof?: Record<string, unknown>;
}

export interface WisePayoutInput {
  transactionId: string;
  accountId: string;
  amount: string;
  currency: "EUR";
  settlementId: string;
  txHash: string;
  providerReference?: string;
}

export interface WisePayoutResult {
  provider: "wise";
  transferId: string;
  payoutReference: string;
  status: string;
  quoteId: string;
  targetAccount: number;
  customerTransactionId: string;
  destination: BankPayoutDestination;
  proof: Record<string, unknown>;
}

export class BankPayoutRail {
  destination(): BankPayoutDestination {
    return {
      bank: process.env.OFFRAMP_BANK_NAME ?? "UNICREDIT",
      iban: process.env.OFFRAMP_BANK_IBAN ?? "IT22B0200822800000103317304",
      bic: process.env.OFFRAMP_BANK_BIC ?? "UNCRITM1305",
      beneficiary: process.env.OFFRAMP_BANK_BENEFICIARY ?? "Massimo Fornara",
    };
  }

  async readiness(amount: string): Promise<BankPayoutReadiness> {
    const destination = this.destination();
    const destinationError = validateDestination(destination);
    if (destinationError) return { ready: false, destination, amount, currency: "EUR", reason: destinationError };
    if (process.env.BANK_PAYOUT_EXECUTION_MODE !== "real") {
      return {
        ready: false,
        destination,
        amount,
        currency: "EUR",
        reason: "BANK_PAYOUT_EXECUTION_MODE must be real before offramp settlement can create a bank payout obligation",
      };
    }
    return this.wiseReadiness(amount, destination);
  }

  async createWisePayout(input: WisePayoutInput): Promise<WisePayoutResult> {
    const readiness = await this.readiness(input.amount);
    if (!readiness.ready) {
      throw new Error(readiness.reason ?? "Wise payout rail is not ready");
    }
    const config = wiseConfig();
    const targetAccount = await this.ensureWiseRecipientAccount(readiness.destination);
    const customerTransactionId = input.transactionId;
    const quote = await wiseFetch(config.baseUrl, "/v3/profiles/" + config.profileId + "/quotes", config.accessToken, {
      method: "POST",
      body: JSON.stringify({
        sourceCurrency: "EUR",
        targetCurrency: "EUR",
        sourceAmount: decimalNumber(input.amount),
        payOut: "BANK_TRANSFER",
        preferredPayIn: "BALANCE",
      }),
    });
    const quoteId = stringField(quote, "id");
    if (!quoteId) throw new Error("Wise quote response missing id");

    const transfer = await wiseFetch(config.baseUrl, "/v1/transfers", config.accessToken, {
      method: "POST",
      body: JSON.stringify({
        targetAccount,
        quoteUuid: quoteId,
        customerTransactionId,
        details: {
          reference: `NeoNoble ${input.transactionId.slice(0, 18)}`,
        },
      }),
    });
    const transferId = stringField(transfer, "id");
    if (!transferId) throw new Error("Wise transfer response missing id");

    const payment = await wiseFetch(config.baseUrl, `/v3/profiles/${config.profileId}/transfers/${transferId}/payments`, config.accessToken, {
      method: "POST",
      body: JSON.stringify({ type: "BALANCE" }),
    });
    const status = stringField(payment, "status") || stringField(transfer, "status") || "accepted";
    return {
      provider: "wise",
      transferId,
      payoutReference: transferId,
      status,
      quoteId,
      targetAccount,
      customerTransactionId,
      destination: readiness.destination,
      proof: {
        type: "wise.balance-funded-transfer",
        quoteId,
        transferId,
        targetAccount,
        paymentStatus: status,
        settlementId: input.settlementId,
        txHash: input.txHash,
        providerReference: input.providerReference,
        observedAt: new Date().toISOString(),
      },
    };
  }

  private async wiseReadiness(amount: string, destination: BankPayoutDestination): Promise<BankPayoutReadiness> {
    const config = wiseConfig();
    if (!config.payoutsEnabled) {
      return { ready: false, destination, amount, currency: "EUR", reason: "WISE_PAYOUTS_ENABLED must be true" };
    }
    const beneficiaryReady = Boolean(config.recipientAccountId || destination.beneficiary);
    if (!config.baseUrl || !config.accessToken || !config.profileId || !beneficiaryReady) {
      return {
        ready: false,
        destination,
        amount,
        currency: "EUR",
        reason: "WISE_BASE_URL, WISE_ACCESS_TOKEN, WISE_PROFILE_ID and beneficiary config are required",
      };
    }
    try {
      const balances = await fetchWiseBalances(config.baseUrl, config.profileId, config.accessToken);
      const eur = balances.find((balance) => String(balance.currency).toUpperCase() === "EUR");
      const available = String(eur?.available ?? "0");
      if (compareDecimal(available, amount) < 0) {
        return {
          ready: false,
          destination,
          amount,
          currency: "EUR",
          reason: `insufficient Wise EUR balance: ${available}/${amount}`,
          proof: { type: "wise.v4.profile.balances", available, balanceId: eur?.id },
        };
      }
      return {
        ready: true,
        provider: "wise",
        destination,
        amount,
        currency: "EUR",
        proof: { type: "wise.v4.profile.balances", available, balanceId: eur?.id, observedAt: new Date().toISOString() },
      };
    } catch (error) {
      return {
        ready: false,
        destination,
        amount,
        currency: "EUR",
        reason: `Wise payout readiness check failed: ${error instanceof Error ? error.message : String(error)}`,
      };
    }
  }

  private async ensureWiseRecipientAccount(destination: BankPayoutDestination): Promise<number> {
    const config = wiseConfig();
    if (config.recipientAccountId) return Number(config.recipientAccountId);
    const account = await wiseFetch(config.baseUrl, "/v1/accounts", config.accessToken, {
      method: "POST",
      body: JSON.stringify({
        profile: Number(config.profileId),
        accountHolderName: destination.beneficiary,
        currency: "EUR",
        type: "iban",
        details: {
          legalType: "PRIVATE",
          IBAN: destination.iban.replace(/\s+/g, ""),
        },
      }),
    });
    const id = Number(asRecord(account).id);
    if (!Number.isFinite(id) || id <= 0) throw new Error("Wise recipient account response missing id");
    return id;
  }
}

function validateDestination(destination: BankPayoutDestination): string | undefined {
  if (!/^IT\d{2}[A-Z0-9]{1}\d{10}[A-Z0-9]{12}$/i.test(destination.iban.replace(/\s+/g, ""))) return "Invalid Italian IBAN";
  if (!/^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$/i.test(destination.bic)) return "Invalid BIC/SWIFT";
  if (!destination.beneficiary.trim()) return "Beneficiary is required";
  return undefined;
}

async function fetchWiseBalances(
  baseUrl: string,
  profileId: string,
  accessToken: string,
): Promise<Array<{ id?: unknown; currency?: unknown; available?: unknown }>> {
  const response = await wiseRawFetch(baseUrl, `/v4/profiles/${profileId}/balances?types=STANDARD`, accessToken);
  const text = await response.text();
  if (!response.ok) throw new Error(`Wise ${response.status}: ${text.slice(0, 300)}`);
  const body = JSON.parse(text) as unknown;
  if (!Array.isArray(body)) throw new Error("Wise balances response is not an array");
  return body.map((balance) => {
    const record = asRecord(balance);
    const currency = asRecord(record.currency).code ?? record.currency;
    return {
      id: record.id,
      currency,
      available: asRecord(record.amount).value ?? record.amount,
    };
  });
}

async function wiseFetch(baseUrl: string, path: string, accessToken: string, init: RequestInit): Promise<unknown> {
  const response = await wiseRawFetch(baseUrl, path, accessToken, init);
  const text = await response.text();
  const body = text ? (JSON.parse(text) as unknown) : {};
  if (!response.ok) throw new Error(`Wise ${response.status}: ${safeJson(body).slice(0, 500)}`);
  return body;
}

async function wiseRawFetch(baseUrl: string, path: string, accessToken: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${baseUrl}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "application/json",
      ...(init.headers ?? {}),
    },
    signal: AbortSignal.timeout(Number(process.env.BANK_PAYOUT_READINESS_TIMEOUT_MS ?? 15_000)),
  });
}

function wiseConfig(): {
  baseUrl: string;
  accessToken: string;
  profileId: string;
  recipientAccountId: string;
  payoutsEnabled: boolean;
} {
  return {
    baseUrl: process.env.WISE_BASE_URL ?? "",
    accessToken: process.env.WISE_ACCESS_TOKEN ?? "",
    profileId: process.env.WISE_PROFILE_ID ?? "",
    recipientAccountId: process.env.WISE_RECIPIENT_ACCOUNT_ID ?? "",
    payoutsEnabled: process.env.WISE_PAYOUTS_ENABLED === "true",
  };
}

function decimalNumber(value: string): number {
  const amount = Number(value);
  if (!Number.isFinite(amount) || amount <= 0) throw new Error(`Invalid payout amount: ${value}`);
  return amount;
}

function stringField(value: unknown, field: string): string | undefined {
  const fieldValue = asRecord(value)[field];
  return fieldValue === undefined || fieldValue === null ? undefined : String(fieldValue);
}

function safeJson(value: unknown): string {
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function compareDecimal(left: string, right: string): number {
  const leftUnits = decimalToUnits(left);
  const rightUnits = decimalToUnits(right);
  return leftUnits === rightUnits ? 0 : leftUnits > rightUnits ? 1 : -1;
}

function decimalToUnits(value: string): bigint {
  const normalized = String(value ?? "0").trim();
  if (!/^\d+(\.\d+)?$/.test(normalized)) return 0n;
  const [whole, fraction = ""] = normalized.split(".");
  return BigInt(`${whole}${fraction.padEnd(2, "0").slice(0, 2)}`);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}
