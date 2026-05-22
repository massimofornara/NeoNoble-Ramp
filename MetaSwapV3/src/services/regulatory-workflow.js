export class RegulatoryWorkflow {
  constructor(eventBus) {
    this.eventBus = eventBus;
    this.controls = new Map([
      ["MiCA_CASP", { status: "evidence_ready", owner: "compliance", evidence: [] }],
      ["EMI_PI", { status: "evidence_ready", owner: "payments", evidence: [] }],
      ["BSA_AML", { status: "evidence_ready", owner: "compliance", evidence: [] }],
      ["SOC2", { status: "evidence_ready", owner: "security", evidence: [] }]
    ]);
  }

  attachEvidence({ control, uri, hash }) {
    const item = this.controls.get(control);
    if (!item) throw new Error("Unknown regulatory control");
    item.evidence.push({ uri, hash, createdAt: new Date().toISOString() });
    this.eventBus.publish("RegulatoryEvidenceAttached", { control, uri, hash });
    return item;
  }

  status() {
    return Object.fromEntries(this.controls.entries());
  }
}
