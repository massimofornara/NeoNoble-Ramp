import type { RpcQuorum } from "./rpcQuorum.js";

export class MempoolMonitor {
  constructor(private readonly quorum: RpcQuorum) {}

  async status(txHash: string): Promise<Record<string, unknown>> {
    const observed = await this.quorum.transaction(txHash);
    return {
      txHash,
      seenBy: observed.responses.length,
      quorum: observed.quorum,
      inMempool: Boolean(observed.transaction && !observed.transaction.blockNumber),
      mined: Boolean(observed.transaction?.blockNumber),
      nonce: observed.transaction?.nonce,
      from: observed.transaction?.from,
    };
  }
}
