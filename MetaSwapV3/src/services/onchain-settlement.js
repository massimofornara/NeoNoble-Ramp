export class OnChainSettlement {
  constructor({ blockchainAdapters, hsm, eventBus }) {
    this.blockchainAdapters = blockchainAdapters;
    this.hsm = hsm;
    this.eventBus = eventBus;
    this.broadcasts = [];
  }

  async estimateGas({ chain, transaction }) {
    const adapter = this.adapter(chain);
    const estimate = await adapter.estimateGas(transaction);
    const result = { chain, estimate };
    this.eventBus.publish("OnChainGasEstimated", result);
    return result;
  }

  async broadcast({ chain, rawTransaction }) {
    const adapter = this.adapter(chain);
    const hash = await adapter.broadcast(rawTransaction);
    const result = { chain, hash, status: "broadcast", createdAt: new Date().toISOString() };
    this.broadcasts.push(result);
    this.eventBus.publish("OnChainTransactionBroadcast", result);
    return result;
  }

  adapter(chain) {
    const adapter = this.blockchainAdapters[chain];
    if (!adapter?.configured()) throw new Error(`RPC is required for ${chain}`);
    return adapter;
  }
}
