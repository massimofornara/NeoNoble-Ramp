export class CustodyService {
  constructor({ ledger, complianceHub, pricingEngine, eventBus, custodyAdapter, hsm }) {
    this.ledger = ledger;
    this.complianceHub = complianceHub;
    this.pricingEngine = pricingEngine;
    this.eventBus = eventBus;
    this.custodyAdapter = custodyAdapter;
    this.hsm = hsm;
    this.withdrawals = [];
  }

  async withdraw({ userId, asset, amount, address, chain }) {
    const user = this.complianceHub.getUser(userId);
    const amountUsd = amount * this.pricingEngine.usdValue(asset);
    const amlScore = this.complianceHub.scoreAml({ user, amountUsd, counterpartyRisk: address?.startsWith("0x000") ? 0.5 : 0 });
    if (amlScore >= 0.75) throw new Error("Withdrawal blocked by AML policy");
    const source = this.ledger.ensureAccount("customer", userId, asset);
    const sink = this.ledger.ensureAccount("external", `${chain}:${address}`, asset);
    if (this.ledger.balance(source).available < Number(amount)) throw new Error(`Insufficient ${asset} balance for withdrawal`);
    this.ledger.lock(source, amount);
    const withdrawal = { id: `wd-${this.withdrawals.length + 1}`, userId, asset, amount, address, chain, status: amountUsd > 25000 ? "pending_mpc_approval" : "submitted" };
    withdrawal.signedEnvelope = this.hsm.signTransaction({
      chain,
      from: `customer:${userId}`,
      to: address,
      asset,
      amount,
      policy: { amlScore, amountUsd, approval: withdrawal.status }
    });
    if (withdrawal.status === "submitted") {
      try {
        withdrawal.externalSubmission = await this.custodyAdapter?.broadcastTransaction({
          withdrawal: { ...withdrawal, signedEnvelope: undefined, externalSubmission: undefined },
          signedEnvelope: withdrawal.signedEnvelope
        });
        const entry = this.ledger.postTransfer({ from: source, fromBucket: "locked", to: sink, asset, amount, memo: "crypto withdrawal" });
        withdrawal.entryId = entry.id;
        withdrawal.status = "broadcast_submitted";
      } catch (error) {
        withdrawal.status = "signed_pending_broadcast";
        withdrawal.broadcastError = error.message;
        this.eventBus.publish("CustodyBroadcastDeferred", { withdrawalId: withdrawal.id, chain, asset, error: error.message });
      }
    }
    this.withdrawals.push(withdrawal);
    this.eventBus.publish("WithdrawalPolicyEvaluated", withdrawal);
    return withdrawal;
  }
}
