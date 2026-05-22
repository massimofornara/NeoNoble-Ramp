import { createHmac, createHash, randomUUID } from "node:crypto";

export class SelfHostedHsm {
  constructor({ masterKey = "metaswap-self-hosted-hsm-master-key", eventBus }) {
    this.masterKey = masterKey;
    this.eventBus = eventBus;
    this.signatures = [];
  }

  signTransaction({ chain, from, to, asset, amount, policy }) {
    const transaction = {
      id: randomUUID(),
      chain,
      from,
      to,
      asset,
      amount,
      policy,
      nonce: this.deriveNonce({ chain, from, to, asset, amount }),
      createdAt: new Date().toISOString()
    };
    const digest = createHash("sha256").update(JSON.stringify(transaction)).digest("hex");
    const signature = createHmac("sha256", this.masterKey).update(digest).digest("hex");
    const envelope = {
      transaction,
      digest,
      signature,
      signer: "self-hosted-hsm",
      status: "signed"
    };
    this.signatures.push(envelope);
    this.eventBus?.publish("CustodyTransactionSigned", envelope);
    return envelope;
  }

  deriveNonce(input) {
    return createHash("sha256").update(JSON.stringify(input)).digest("hex").slice(0, 16);
  }
}
