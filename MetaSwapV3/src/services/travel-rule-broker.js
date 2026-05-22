import { randomUUID } from "node:crypto";

export class TravelRuleBroker {
  constructor({ eventBus }) {
    this.eventBus = eventBus;
    this.messages = [];
  }

  createTransferMessage({ originator, beneficiary, asset, amount, destination }) {
    const message = {
      id: randomUUID(),
      standard: "IVMS101",
      originator,
      beneficiary,
      asset,
      amount,
      destination,
      status: "ready_for_counterparty_delivery",
      createdAt: new Date().toISOString()
    };
    this.messages.push(message);
    this.eventBus.publish("TravelRuleMessageCreated", message);
    return message;
  }
}
