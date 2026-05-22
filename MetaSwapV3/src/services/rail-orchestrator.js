export class RailOrchestrator {
  constructor({ providerRegistry, bankingAdapter, cardAdapter, eventBus }) {
    this.providerRegistry = providerRegistry;
    this.bankingAdapter = bankingAdapter;
    this.cardAdapter = cardAdapter;
    this.eventBus = eventBus;
  }

  async submitPayout(instruction) {
    const rail = instruction.rail;
    const provider = this.providerRegistry.select({ kind: "fiat_rail", capability: rail });
    const enriched = { ...instruction, providerId: provider.id };
    let response;
    try {
      if (rail === "SEPA") response = await this.bankingAdapter.submitSepaPayout(enriched);
      else if (rail === "SWIFT") response = await this.bankingAdapter.submitSwiftPayout(enriched);
      else if (rail === "CARD") response = await this.cardAdapter.submitPayout(enriched);
      else throw new Error(`Unsupported payout rail ${rail}`);
      this.eventBus.publish("RailInstructionSubmitted", { reference: instruction.reference, rail, providerId: provider.id, response });
    } catch (error) {
      this.eventBus.publish("RailInstructionDeferred", { reference: instruction.reference, rail, providerId: provider.id, error: error.message });
      throw error;
    }
    const result = { provider, response, status: "submitted" };
    return result;
  }
}
