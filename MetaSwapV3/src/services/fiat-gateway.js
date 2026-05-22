export class FiatGateway {
  constructor({ ledger, complianceHub, pricingEngine, eventBus, railOrchestrator, travelRuleBroker, revenueEngine }) {
    this.ledger = ledger;
    this.complianceHub = complianceHub;
    this.pricingEngine = pricingEngine;
    this.eventBus = eventBus;
    this.railOrchestrator = railOrchestrator;
    this.travelRuleBroker = travelRuleBroker;
    this.revenueEngine = revenueEngine;
    this.reconciliation = [];
  }

  deposit({ userId, asset = "EUR", amount, rail = "SEPA", reference = `dep-${Date.now()}` }) {
    if (process.env.METASWAP_ENV === "production" && !reference.startsWith("wise-") && !reference.startsWith("bank-") && !reference.startsWith("sepa-")) {
      throw new Error("Production fiat deposit requires a confirmed external rail reference");
    }
    const user = this.complianceHub.getUser(userId);
    const amountUsd = amount * this.pricingEngine.usdValue(asset);
    const amlScore = this.complianceHub.scoreAml({ user, amountUsd, rail: rail.toLowerCase() });
    if (amlScore >= 0.85) throw new Error("Deposit held by AML policy");
    const external = this.ledger.ensureAccount("external", `${rail}-inbound`, asset);
    this.ledger.credit(external, "available", amount);
    const customer = this.ledger.ensureAccount("customer", userId, asset);
    const entry = this.ledger.postTransfer({ from: external, to: customer, asset, amount, memo: `fiat deposit ${rail}` });
    this.reconciliation.push({ reference, type: "deposit", rail, asset, amount, status: "matched", entryId: entry.id });
    this.eventBus.publish("FiatDepositSettled", { userId, asset, amount, rail, reference });
    return { reference, status: "settled", entryId: entry.id, amlScore };
  }

  async payout({ userId, asset = "EUR", amount, rail = "SEPA", destination }) {
    const user = this.complianceHub.getUser(userId);
    if (!destination?.name) throw new Error("Destination name required");
    const amountUsd = amount * this.pricingEngine.usdValue(asset);
    const amlScore = this.complianceHub.scoreAml({ user, amountUsd, rail: rail.toLowerCase() });
    if (amlScore >= 0.75) {
      this.complianceHub.openCase("PAYOUT_AML", userId, "Payout requires enhanced review", "high");
      throw new Error("Payout held by AML policy");
    }
    const customer = this.ledger.ensureAccount("customer", userId, asset);
    const fee = this.revenueEngine?.fiatPayoutFee({ asset, amount }) ?? { feeAmount: 0, asset };
    if (this.ledger.balance(customer).available < Number(amount) + Number(fee.feeAmount)) {
      throw new Error(`Insufficient ${asset} balance for payout`);
    }
    const external = this.ledger.ensureAccount("external", `${rail}-outbound`, asset);
    const reference = `pay-${Date.now()}`;
    const travelRuleMessage = this.travelRuleBroker?.createTransferMessage({
      originator: { id: userId, name: user.name, jurisdiction: user.jurisdiction },
      beneficiary: destination,
      asset,
      amount,
      destination
    });
    const instruction = { reference, userId, asset, amount, rail, destination, travelRuleMessageId: travelRuleMessage?.id };
    const externalSubmission = await this.railOrchestrator.submitPayout(instruction);
    const entry = this.ledger.postTransfer({ from: customer, to: external, asset, amount, memo: `fiat payout ${rail}` });
    const feeEntry = this.revenueEngine?.recordFee({ fee, from: customer, memo: "fiat payout fee" });
    this.reconciliation.push({ reference, type: "payout", rail, asset, amount, fee, status: "submitted", entryId: entry.id, feeEntryId: feeEntry?.id, destination, externalSubmission, travelRuleMessageId: travelRuleMessage?.id });
    this.eventBus.publish("FiatPayoutSubmitted", { userId, asset, amount, fee, rail, reference, externalSubmission, travelRuleMessageId: travelRuleMessage?.id });
    return { reference, status: "submitted", entryId: entry.id, feeEntryId: feeEntry?.id, fee, amlScore, externalSubmission, travelRuleMessage };
  }
}
