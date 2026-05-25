import type { EventBus, ReconciliationReport } from "../core/types.js";
import { decimalToUnits, type EventStore, type LedgerStore, type SettlementProofStore } from "../core/store.js";
import { metrics } from "../core/observability.js";
import { hasEvent, rebuildState } from "../core/stateMachine.js";

export class ReconciliationEngine {
  constructor(
    private readonly bus: EventBus,
    private readonly events: EventStore,
    private readonly ledger: LedgerStore,
    private readonly settlementProofs: SettlementProofStore,
  ) {}

  async reconcile(transactionId: string): Promise<ReconciliationReport> {
    await this.bus.publish("reconciliation.requested", transactionId, {
      requestedBy: "api",
    });

    const events = this.events.byTransaction(transactionId);
    const ledgerEntries = this.ledger.byTransaction(transactionId);
    const state = rebuildState(events);
    const settlementConfirmationExists = hasEvent(events, "settlement.confirmed");
    const settlementPendingConfirmation = hasEvent(events, "settlement.pending_confirmation");
    const settlementFailed = hasEvent(events, "settlement.failed");
    const executionFailed = hasEvent(events, "execution.failed");
    const ledgerReconciled = hasEvent(events, "ledger.append");
    const ledgerHash = this.ledger.verifyHashChain();
    const eventReplayValid = this.replayDeterministically(events);
    const settlementProofHash = this.settlementProofs.verifyHashChain();
    const immutableSettlementProof = this.verifyImmutableSettlementProof(transactionId, events);
    const settlementProofValid = this.verifySettlementProof(events) && immutableSettlementProof && settlementProofHash.valid;
    const ledgerConsistent = settlementConfirmationExists
      ? ledgerEntries.length >= 2 &&
        ledgerEntries.some((entry) => entry.accountId !== "exchange-clearing") &&
        ledgerEntries.reduce((sum, entry) => sum + decimalToUnits(entry.delta), 0n) === 0n
      : ledgerEntries.length === 0;

    const errors = [...state.errors];
    errors.push(...ledgerHash.errors);
    errors.push(...settlementProofHash.errors);
    if (settlementConfirmationExists && !ledgerConsistent) {
      errors.push("Settlement exists but ledger entries are missing or incomplete");
    }
    if (!settlementConfirmationExists && ledgerEntries.length > 0) {
      errors.push("Ledger has entries before settlement confirmation");
    }
    if ((settlementFailed || executionFailed) && ledgerEntries.length > 0) {
      errors.push("Failed transaction has ledger entries");
    }
    if (settlementPendingConfirmation && !this.verifyPendingSettlement(events)) {
      errors.push("Pending settlement confirmation is missing a valid txHash/settlementId");
    }
    if (!settlementProofValid && settlementConfirmationExists) {
      errors.push("Settlement confirmation does not match initiated txHash/settlementId or immutable receipt proof");
    }

    const integrity =
      state.valid &&
      ledgerHash.valid &&
      eventReplayValid &&
      settlementProofValid &&
      immutableSettlementProof &&
      ledgerConsistent &&
      (!settlementPendingConfirmation || this.verifyPendingSettlement(events)) &&
      (settlementConfirmationExists ? ledgerReconciled : true);
    if (!integrity && settlementConfirmationExists) {
      metrics.inc("exchange_reconciliation_integrity_failures_total", { transactionId });
    }

    return {
      transactionId,
      status: settlementFailed || executionFailed || errors.length > 0 ? "failed" : integrity && settlementConfirmationExists ? "settlement_confirmed" : "pending",
      integrity,
      ledgerIntegrity: ledgerHash.valid && ledgerConsistent,
      eventReplayValid,
      settlementProofValid,
      state: state.state,
      checks: {
        stateMachineValid: state.valid,
        ledgerConsistent,
        settlementConfirmationExists,
        ledgerReconciled,
        immutableSettlementProof,
      },
      events,
      ledgerEntries,
      errors,
    };
  }

  private replayDeterministically(events: Array<{ type: string; offset?: number }>): boolean {
    const sorted = [...events].sort((a, b) => Number(a.offset ?? 0) - Number(b.offset ?? 0));
    return sorted.every((event, index) => event === events[index]);
  }

  private verifySettlementProof(events: Array<{ type: string; payload: Record<string, unknown> }>): boolean {
    const confirmed = events.find((event) => event.type === "settlement.confirmed");
    if (!confirmed) return true;
    const initiated = settlementAnchor(events, confirmed);
    if (!initiated) return false;
    const initiatedTxHash = String(initiated.payload.txHash || "");
    const confirmedTxHash = String(confirmed.payload.txHash || "");
    const initiatedSettlementId = String(initiated.payload.settlementId || "");
    const confirmedSettlementId = String(confirmed.payload.settlementId || "");
    return (
      validTransactionReference(confirmedTxHash, String(confirmed.payload.adapter ?? initiated.payload.adapter ?? "")) &&
      initiatedTxHash === confirmedTxHash &&
      initiatedSettlementId === confirmedSettlementId &&
      Number(confirmed.payload.observedConfirmations ?? 0) >= Number(confirmed.payload.requiredConfirmations ?? 1)
    );
  }

  private verifyPendingSettlement(events: Array<{ type: string; payload: Record<string, unknown> }>): boolean {
    const pending = events.find((event) => event.type === "settlement.pending_confirmation");
    if (!pending) return true;
    const initiated = settlementAnchor(events, pending);
    if (!initiated) return false;
    const txHash = String(pending.payload.txHash || "");
    const settlementId = String(pending.payload.settlementId || "");
    return (
      validTransactionReference(txHash, String(pending.payload.adapter ?? initiated.payload.adapter ?? "")) &&
      txHash === String(initiated.payload.txHash || "") &&
      settlementId.length > 0 &&
      settlementId === String(initiated.payload.settlementId || "")
    );
  }

  private verifyImmutableSettlementProof(transactionId: string, events: Array<{ type: string; payload: Record<string, unknown> }>): boolean {
    const confirmed = events.find((event) => event.type === "settlement.confirmed");
    if (!confirmed) return true;
    const proof = this.settlementProofs.latestConfirmed(transactionId);
    if (!proof) return false;
    return (
      proof.status === "confirmed" &&
      proof.receiptStatus === "success" &&
      proof.txHash === String(confirmed.payload.txHash) &&
      proof.settlementId === String(confirmed.payload.settlementId) &&
      proof.currentHash === String(confirmed.payload.settlementProofHash) &&
      proof.observedConfirmations >= proof.requiredConfirmations
    );
  }
}

function validTransactionReference(value: string, adapter: string): boolean {
  if (adapter === "solana") return /^[1-9A-HJ-NP-Za-km-z]{32,96}$/.test(value);
  return /^0x[a-f0-9]{64}$/i.test(value);
}

function settlementAnchor(
  events: Array<{ type: string; payload: Record<string, unknown> }>,
  before: { type: string; payload: Record<string, unknown> },
): { type: string; payload: Record<string, unknown> } | undefined {
  const index = events.indexOf(before);
  const candidates = (index >= 0 ? events.slice(0, index) : events).filter(
    (event) => event.type === "settlement.initiated" || event.type === "settlement.replacement_broadcast",
  );
  return candidates.at(-1);
}
