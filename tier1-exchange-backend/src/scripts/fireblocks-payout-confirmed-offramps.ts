import "../core/env.js";
import { createTier1ExchangeApp } from "../app.js";
import { FireblocksClient } from "../services/fireblocksClient.js";

type PayoutAccountType = "VAULT_ACCOUNT" | "EXCHANGE_ACCOUNT" | "FIAT_ACCOUNT";
type PayeeAccountType = PayoutAccountType | "EXTERNAL_WALLET" | "NETWORK_CONNECTION" | "MERCHANT_ACCOUNT";

interface Candidate {
  transactionId: string;
  accountId: string;
  amount: string;
  assetId: string;
  settlementId: string;
  txHash: string;
}

async function main(): Promise<void> {
  const client = FireblocksClient.fromEnv();
  const paymentAccount = payoutPaymentAccount();
  const payeeAccount = payoutPayeeAccount();
  const destination = beneficiary();
  const app = createTier1ExchangeApp({ dataDir: process.env.TIER1_DATA_DIR || "./data" });
  await app.store.ready();
  const candidates = await settlementConfirmedOfframps(app);
  const results = [];

  for (const candidate of candidates) {
    const existing = app.store.events
      .byTransaction(candidate.transactionId)
      .find((event) => event.type === "payout.confirmed" || event.type === "payout.initiated");
    if (existing) {
      results.push({ transactionId: candidate.transactionId, status: "skipped", reason: `existing ${existing.type}` });
      continue;
    }

    const createKey = `fireblocks-payout-create:${candidate.transactionId}`;
    const executeKey = `fireblocks-payout-execute:${candidate.transactionId}`;
    const payout = await client.createPayout(
      {
        paymentAccount,
        instructionSet: [
          {
            name: `Massimo Fornara offramp ${candidate.transactionId}`,
            payeeAccount,
            amount: {
              amount: candidate.amount,
              assetId: candidate.assetId,
            },
          },
        ],
      },
      createKey,
    );
    const payoutId = stringField(payout, "payoutId");
    if (!payoutId) throw new Error(`Fireblocks payout creation did not return payoutId for ${candidate.transactionId}`);
    await app.bus.publish("payout.initiated", candidate.transactionId, {
      provider: "fireblocks-payments",
      payoutId,
      paymentAccount,
      payeeAccount,
      destination,
      assetId: candidate.assetId,
      amount: candidate.amount,
      settlementId: candidate.settlementId,
      txHash: candidate.txHash,
      providerProof: redact(payout),
    });

    const executed = await client.executePayout(payoutId, executeKey);
    const final = await waitForPayoutFinality(client, payoutId);
    const state = normalize(stringField(final, "state") ?? stringField(executed, "state") ?? "");
    const status = normalize(stringField(final, "status") ?? stringField(executed, "status") ?? "");
    if (!(state === "FINALIZED" && status === "DONE")) {
      results.push({ transactionId: candidate.transactionId, status: "pending", payoutId, fireblocksState: state, fireblocksStatus: status });
      continue;
    }

    await app.bus.publish("payout.confirmed", candidate.transactionId, {
      provider: "fireblocks-payments",
      payoutId,
      payoutReference: payoutId,
      paymentAccount,
      payeeAccount,
      destination,
      assetId: candidate.assetId,
      amount: candidate.amount,
      settlementId: candidate.settlementId,
      txHash: candidate.txHash,
      providerStatus: status,
      providerState: state,
      providerProof: redact(final),
    });
    await app.ledgerService.append({
      idempotencyKey: `fireblocks-payout:${candidate.transactionId}:${payoutId}:user-debit`,
      transactionId: candidate.transactionId,
      accountId: candidate.accountId,
      asset: candidate.assetId,
      amount: `-${candidate.amount}`,
      direction: "debit",
      reason: "fireblocks_payout_confirmed_user_debit",
      metadata: { payoutId, destination },
    });
    await app.ledgerService.append({
      idempotencyKey: `fireblocks-payout:${candidate.transactionId}:${payoutId}:bank-credit`,
      transactionId: candidate.transactionId,
      accountId: "fireblocks-payments-clearing",
      asset: candidate.assetId,
      amount: candidate.amount,
      direction: "credit",
      reason: "fireblocks_payout_confirmed_bank_credit",
      metadata: { payoutId, destination },
    });
    results.push({ transactionId: candidate.transactionId, status: "payout_confirmed", payoutId, destination });
  }

  console.log(JSON.stringify({ mode: "fireblocks-payout-confirmed-offramps", destination, count: results.length, results }, null, 2));
}

async function settlementConfirmedOfframps(app: ReturnType<typeof createTier1ExchangeApp>): Promise<Candidate[]> {
  const transactionIds = [...new Set(app.store.events.all().map((event) => event.transactionId))];
  const candidates: Candidate[] = [];
  for (const transactionId of transactionIds) {
    const events = app.store.events.byTransaction(transactionId);
    const created = events.find((event) => event.type === "execution.intent_created" || event.type === "orders.created");
    if (created?.payload.type !== "offramp") continue;
    const report = await app.reconciliationEngine.reconcile(transactionId);
    await app.bus.drain();
    if (report.status !== "settlement_confirmed" || !report.integrity) continue;
    const confirmed = app.store.events.byTransaction(transactionId).find((event) => event.type === "settlement.confirmed");
    const initiated = app.store.events.byTransaction(transactionId).find((event) => event.type === "settlement.initiated");
    if (!confirmed || !initiated) continue;
    candidates.push({
      transactionId,
      accountId: String(created.payload.accountId ?? "unknown-account"),
      amount: String(initiated.payload.amount ?? created.payload.expectedToAmount ?? ""),
      assetId: String(process.env.FIREBLOCKS_PAYOUT_ASSET_ID ?? initiated.payload.asset ?? created.payload.toAsset ?? "EUR"),
      settlementId: String(confirmed.payload.settlementId),
      txHash: String(confirmed.payload.txHash),
    });
  }
  return candidates;
}

async function waitForPayoutFinality(client: FireblocksClient, payoutId: string): Promise<Record<string, unknown>> {
  const attempts = Number(process.env.FIREBLOCKS_PAYOUT_POLL_ATTEMPTS ?? 12);
  const delayMs = Number(process.env.FIREBLOCKS_PAYOUT_POLL_DELAY_MS ?? 5000);
  let latest = await client.getPayout(payoutId);
  for (let attempt = 1; attempt < attempts; attempt += 1) {
    const state = normalize(stringField(latest, "state") ?? "");
    const status = normalize(stringField(latest, "status") ?? "");
    if (state === "FINALIZED" && status === "DONE") return latest;
    if (state === "FAILED" || status === "FAILED") throw new Error(`Fireblocks payout failed: ${JSON.stringify(redact(latest))}`);
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    latest = await client.getPayout(payoutId);
  }
  return latest;
}

function payoutPaymentAccount(): { id: string; type: PayoutAccountType } {
  const id = required("FIREBLOCKS_PAYMENT_ACCOUNT_ID");
  const type = accountType(required("FIREBLOCKS_PAYMENT_ACCOUNT_TYPE"), ["VAULT_ACCOUNT", "EXCHANGE_ACCOUNT", "FIAT_ACCOUNT"]);
  return { id, type: type as PayoutAccountType };
}

function payoutPayeeAccount(): { id: string; type: PayeeAccountType } {
  const id = required("FIREBLOCKS_MASSIMO_FORNARA_PAYEE_ACCOUNT_ID");
  const type = accountType(required("FIREBLOCKS_MASSIMO_FORNARA_PAYEE_ACCOUNT_TYPE"), [
    "VAULT_ACCOUNT",
    "EXCHANGE_ACCOUNT",
    "FIAT_ACCOUNT",
    "EXTERNAL_WALLET",
    "NETWORK_CONNECTION",
    "MERCHANT_ACCOUNT",
  ]);
  return { id, type: type as PayeeAccountType };
}

function beneficiary(): Record<string, string> {
  return {
    bank: process.env.OFFRAMP_BANK_NAME || "UNICREDIT",
    iban: process.env.OFFRAMP_BANK_IBAN || "IT22B0200822800000103317304",
    bic: process.env.OFFRAMP_BANK_BIC || "UNCRITM1305",
    beneficiary: process.env.OFFRAMP_BANK_BENEFICIARY || "Massimo Fornara",
    fireblocksPayeeAccountId: process.env.FIREBLOCKS_MASSIMO_FORNARA_PAYEE_ACCOUNT_ID || "",
  };
}

function required(key: string): string {
  const value = process.env[key];
  if (!value) throw new Error(`${key} is required for Fireblocks Payments payout execution`);
  return value;
}

function accountType(value: string, allowed: string[]): string {
  const normalized = value.toUpperCase();
  if (!allowed.includes(normalized)) throw new Error(`Unsupported Fireblocks payout account type: ${value}`);
  return normalized;
}

function stringField(value: Record<string, unknown>, field: string): string | undefined {
  const candidate = value[field];
  return typeof candidate === "string" && candidate.length > 0 ? candidate : undefined;
}

function normalize(value: string): string {
  return value.trim().toUpperCase();
}

function redact(value: unknown): unknown {
  return JSON.parse(JSON.stringify(value, (key, inner) => (/secret|key|token|authorization|signature/i.test(key) ? "[redacted]" : inner)));
}

main().catch((error) => {
  console.error(
    JSON.stringify({
      level: "error",
      component: "fireblocks-payout-confirmed-offramps",
      error: error instanceof Error ? error.message : String(error),
    }),
  );
  process.exitCode = 1;
});
