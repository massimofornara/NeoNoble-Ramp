export class ReconciliationEngine {
  constructor({ ledger, fiatGateway, eventBus }) {
    this.ledger = ledger;
    this.fiatGateway = fiatGateway;
    this.eventBus = eventBus;
  }

  run() {
    const unmatched = [];
    for (const item of this.fiatGateway.reconciliation) {
      const entry = this.ledger.journal.find((row) => row.id === item.entryId);
      if (!entry) unmatched.push({ reference: item.reference, reason: "MISSING_LEDGER_ENTRY" });
    }
    const result = {
      status: unmatched.length ? "exceptions" : "matched",
      checked: this.fiatGateway.reconciliation.length,
      unmatched,
      createdAt: new Date().toISOString()
    };
    this.eventBus.publish("ReconciliationCompleted", result);
    return result;
  }
}
