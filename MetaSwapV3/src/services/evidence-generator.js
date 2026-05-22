import { createHash } from "node:crypto";

export class EvidenceGenerator {
  constructor({ eventBus, ledger, proofService, regulatoryWorkflow }) {
    this.eventBus = eventBus;
    this.ledger = ledger;
    this.proofService = proofService;
    this.regulatoryWorkflow = regulatoryWorkflow;
  }

  generate(control) {
    const payload = {
      control,
      generatedAt: new Date().toISOString(),
      ledgerHash: this.ledger.lastHash,
      journalEntries: this.ledger.journal.length,
      proof: this.proofService.reservesAndLiabilities(),
      recentEvents: this.eventBus.tail(50)
    };
    const hash = createHash("sha256").update(JSON.stringify(payload)).digest("hex");
    const uri = `evidence://${control}/${hash}`;
    this.regulatoryWorkflow.attachEvidence({ control, uri, hash });
    this.eventBus.publish("RegulatoryEvidenceGenerated", { control, uri, hash });
    return { uri, hash, payload };
  }
}
