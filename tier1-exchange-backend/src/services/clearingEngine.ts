import { ClearingQueue, type ClearingItem } from "./clearingQueue.js";
import { NetSettlementEngine } from "./netSettlementEngine.js";

export interface ClearingPlan {
  delayedBatchSettlement: boolean;
  nettedTransfers: Array<{ asset: string; netAmount: string }>;
  onChainFootprintReduction: boolean;
}

export class ClearingEngine {
  constructor(
    private readonly queue = new ClearingQueue(),
    private readonly netSettlement = new NetSettlementEngine(),
  ) {}

  plan(intentId: string, legs: ClearingItem[]): ClearingPlan {
    for (const leg of legs) this.queue.enqueue({ ...leg, intentId });
    const nettedTransfers = this.netSettlement.net(this.queue.pending());
    return {
      delayedBatchSettlement: nettedTransfers.length > 1,
      nettedTransfers,
      onChainFootprintReduction: legs.length > nettedTransfers.length,
    };
  }
}
