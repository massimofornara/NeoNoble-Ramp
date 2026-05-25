import "../core/env.js";

import { createTier1ExchangeApp } from "../app.js";
import type { DomainEvent } from "../core/types.js";
import { BankPayoutRail } from "../services/bankPayoutRail.js";
import { DirectSepaPayoutRail } from "../services/directSepaPayoutRail.js";
import { ModulrPayoutRail } from "../services/modulrPayoutRail.js";

interface PayoutRunResult {
  transactionId: string;
  status: "payout_confirmed" | "skipped" | "blocked" | "payout_failed";
  amount?: string;
  currency?: string;
  accountId?: string;
  settlementId?: string;
  txHash?: string;
  provider?: string;
  payoutReference?: string;
  reason?: string;
  reconciliationIntegrity?: boolean;
}

const EXECUTION_FLAG = "PAYOUT_EXECUTE_CONFIRMED_OFFRAMPS";

async function main(): Promise<void> {
  if (process.env[EXECUTION_FLAG] !== "1") {
    throw new Error(`${EXECUTION_FLAG}=1 is required to create real bank transfers/payouts`);
  }

  const app = createTier1ExchangeApp();
  await app.store.ready();
  const payoutRail = payoutRailForEnv();
  const candidates = selectConfirmedOfframps(app.store.events.all(), process.env.PAYOUT_TRANSACTION_IDS);
  const results: PayoutRunResult[] = [];

  for (const candidate of candidates) {
    const events = app.store.events.byTransaction(candidate.transactionId);
    const existingPayout = events.find((event) => event.type === "payout.confirmed" || event.type === "payout.initiated");
    if (existingPayout) {
      results.push({
        transactionId: candidate.transactionId,
        status: "skipped",
        reason: `existing ${existingPayout.type} event`,
      });
      continue;
    }

    const report = await app.reconciliationEngine.reconcile(candidate.transactionId);
    await app.bus.drain();
    if (report.status !== "settlement_confirmed" || !report.integrity) {
      results.push({
        transactionId: candidate.transactionId,
        status: "blocked",
        reason: "reconciliation is not settlement_confirmed with integrity=true",
        reconciliationIntegrity: report.integrity,
      });
      continue;
    }

    const refreshed = app.store.events.byTransaction(candidate.transactionId);
    const intent = firstEvent(refreshed, "execution.intent_created");
    const initiated = firstEvent(refreshed, "settlement.initiated");
    const confirmed = firstEvent(refreshed, "settlement.confirmed");
    const amount = stringPayload(initiated, "amount");
    const asset = stringPayload(initiated, "asset");
    const accountId = stringPayload(intent, "accountId") ?? "unknown-account";
    const settlementId = stringPayload(confirmed, "settlementId") ?? stringPayload(initiated, "settlementId") ?? "";
    const txHash = stringPayload(confirmed, "txHash") ?? stringPayload(initiated, "txHash") ?? "";

    if (asset !== "EUR" || !amount || !settlementId || !txHash) {
      results.push({
        transactionId: candidate.transactionId,
        status: "blocked",
        amount,
        currency: asset,
        accountId,
        settlementId,
        txHash,
        reason: "confirmed off-ramp is missing EUR amount, settlementId, or txHash",
        reconciliationIntegrity: report.integrity,
      });
      continue;
    }

    const readiness = await payoutRail.readiness(amount);
    if (!readiness.ready) {
      results.push({
        transactionId: candidate.transactionId,
        status: "blocked",
        amount,
        currency: "EUR",
        accountId,
        settlementId,
        txHash,
        reason: readiness.reason ?? "bank payout rail is not ready",
        reconciliationIntegrity: report.integrity,
      });
      continue;
    }

    const payoutIntent = await app.bus.publish("payout.initiated", candidate.transactionId, {
      provider: readiness.provider,
      amount,
      currency: "EUR",
      accountId,
      settlementId,
      txHash,
      destination: readiness.destination,
      readinessProof: readiness.proof,
    });
    await app.bus.drain();

    try {
      const payout = await payoutRail.createPayout({
        transactionId: candidate.transactionId,
        accountId,
        amount,
        currency: "EUR",
        settlementId,
        txHash,
        providerReference: stringPayload(confirmed, "providerReference"),
      });
      await app.bus.publish("payout.confirmed", candidate.transactionId, {
        provider: payout.provider,
        amount,
        currency: "EUR",
        accountId,
        settlementId,
        txHash,
        payoutReference: payout.payoutReference,
        providerStatus: payout.status,
        customerTransactionId: payout.customerTransactionId,
        quoteId: payout.quoteId,
        targetAccount: payout.targetAccount,
        destination: payout.destination,
        providerProof: payout.proof,
        payoutInitiatedEventId: payoutIntent.eventId,
      });
      await app.ledgerService.append({
        idempotencyKey: `payout:${candidate.transactionId}:${payout.payoutReference}:user-debit`,
        transactionId: candidate.transactionId,
        accountId,
        asset: "EUR",
        amount,
        direction: "debit",
        reason: "payout_confirmed_user_debit",
        metadata: {
          provider: payout.provider,
          payoutReference: payout.payoutReference,
          settlementId,
          txHash,
        },
      });
      await app.ledgerService.append({
        idempotencyKey: `payout:${candidate.transactionId}:${payout.payoutReference}:bank-clearing-credit`,
        transactionId: candidate.transactionId,
        accountId: "bank-payout-clearing",
        asset: "EUR",
        amount,
        direction: "credit",
        reason: "payout_confirmed_bank_clearing_credit",
        metadata: {
          provider: payout.provider,
          payoutReference: payout.payoutReference,
          settlementId,
          txHash,
        },
      });
      await app.bus.drain();
      const postPayoutReport = await app.reconciliationEngine.reconcile(candidate.transactionId);
      results.push({
        transactionId: candidate.transactionId,
        status: "payout_confirmed",
        amount,
        currency: "EUR",
        accountId,
        settlementId,
        txHash,
        provider: payout.provider,
        payoutReference: payout.payoutReference,
        reconciliationIntegrity: postPayoutReport.integrity,
      });
    } catch (error) {
      const reason = error instanceof Error ? error.message : String(error);
      await app.bus.publish("payout.failed", candidate.transactionId, {
        provider: readiness.provider,
        amount,
        currency: "EUR",
        accountId,
        settlementId,
        txHash,
        retryable: true,
        reason,
        payoutInitiatedEventId: payoutIntent.eventId,
      });
      results.push({
        transactionId: candidate.transactionId,
        status: "payout_failed",
        amount,
        currency: "EUR",
        accountId,
        settlementId,
        txHash,
        provider: readiness.provider,
        reason,
        reconciliationIntegrity: report.integrity,
      });
    }
  }

  const summary = {
    mode: "create-confirmed-offramp-payouts",
    provider: payoutRail.provider,
    executionMode: process.env.BANK_PAYOUT_EXECUTION_MODE ?? "not_configured",
    destination: payoutRail.destination(),
    totals: {
      candidates: candidates.length,
      confirmed: results.filter((result) => result.status === "payout_confirmed").length,
      blocked: results.filter((result) => result.status === "blocked").length,
      skipped: results.filter((result) => result.status === "skipped").length,
      failed: results.filter((result) => result.status === "payout_failed").length,
    },
    results,
  };
  console.log(JSON.stringify(summary, null, 2));
  if (summary.totals.failed > 0) process.exitCode = 1;
}

function payoutRailForEnv(): {
  provider: string;
  destination(): ReturnType<BankPayoutRail["destination"]>;
  readiness(amount: string): Promise<{
    ready: boolean;
    provider?: string;
    destination: ReturnType<BankPayoutRail["destination"]>;
    amount: string;
    currency: "EUR";
    reason?: string;
    proof?: Record<string, unknown>;
  }>;
  createPayout(input: {
    transactionId: string;
    accountId: string;
    amount: string;
    currency: "EUR";
    settlementId: string;
    txHash: string;
    providerReference?: string;
  }): Promise<{
    provider: string;
    payoutReference: string;
    status: string;
    customerTransactionId?: string;
    quoteId?: string;
    targetAccount?: number;
    destination: ReturnType<BankPayoutRail["destination"]>;
    proof: Record<string, unknown>;
  }>;
} {
  const rail = String(process.env.PAYOUT_RAIL ?? process.env.BANK_RAIL_PROVIDER ?? "direct-sepa").toLowerCase();
  if (rail === "wise") {
    const wise = new BankPayoutRail();
    return {
      provider: "wise",
      destination: () => wise.destination(),
      readiness: (amount) => wise.readiness(amount),
      createPayout: (input) => wise.createWisePayout(input),
    };
  }
  if (rail === "modulr") {
    const modulr = new ModulrPayoutRail();
    return {
      provider: "modulr",
      destination: () => modulr.destination(),
      readiness: (amount) => modulr.readiness(amount),
      createPayout: (input) => modulr.createPayout(input),
    };
  }
  const directSepa = new DirectSepaPayoutRail();
  return {
    provider: "direct-sepa",
    destination: () => directSepa.destination(),
    readiness: (amount) => directSepa.readiness(amount),
    createPayout: (input) => directSepa.createPayout(input),
  };
}

function selectConfirmedOfframps(events: DomainEvent[], filter?: string): Array<{ transactionId: string }> {
  const ids = new Set((filter ?? "").split(",").map((id) => id.trim()).filter(Boolean));
  const byTransaction = new Map<string, DomainEvent[]>();
  for (const event of events) {
    byTransaction.set(event.transactionId, [...(byTransaction.get(event.transactionId) ?? []), event]);
  }
  return [...byTransaction.entries()]
    .filter(([transactionId, transactionEvents]) => {
      if (ids.size > 0 && !ids.has(transactionId)) return false;
      const intent = firstEvent(transactionEvents, "execution.intent_created");
      const initiated = firstEvent(transactionEvents, "settlement.initiated");
      return (
        stringPayload(intent, "type") === "offramp" &&
        stringPayload(initiated, "asset") === "EUR" &&
        transactionEvents.some((event) => event.type === "settlement.confirmed")
      );
    })
    .map(([transactionId]) => ({ transactionId }));
}

function firstEvent(events: DomainEvent[], type: DomainEvent["type"]): DomainEvent | undefined {
  return events.find((event) => event.type === type);
}

function stringPayload(event: DomainEvent | undefined, key: string): string | undefined {
  const value = event?.payload[key];
  return value === undefined || value === null ? undefined : String(value);
}

main().catch((error) => {
  console.error(
    JSON.stringify({
      level: "error",
      component: "create-offramp-payouts",
      error: error instanceof Error ? error.message : String(error),
    }),
  );
  process.exitCode = 1;
});
