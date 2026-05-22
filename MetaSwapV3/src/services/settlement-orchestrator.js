export class SettlementOrchestrator {
  constructor({ ledger, fiatGateway, custodyService, eventBus }) {
    this.ledger = ledger;
    this.fiatGateway = fiatGateway;
    this.custodyService = custodyService;
    this.eventBus = eventBus;
  }

  status() {
    const fiat = this.fiatGateway.reconciliation.map((item) => ({
      type: item.type,
      reference: item.reference,
      rail: item.rail,
      status: item.status,
      ledgerEntryId: item.entryId
    }));
    const custody = this.custodyService.withdrawals.map((item) => ({
      type: "custody_withdrawal",
      reference: item.id,
      rail: item.chain,
      status: item.status,
      ledgerEntryId: item.entryId,
      signed: Boolean(item.signedEnvelope?.signature)
    }));
    const result = {
      generatedAt: new Date().toISOString(),
      ledgerEntries: this.ledger.journal.length,
      pending: [...fiat, ...custody].filter((item) => !["matched", "broadcast"].includes(item.status)),
      fiat,
      custody
    };
    this.eventBus.publish("SettlementStatusGenerated", result);
    return result;
  }
}
