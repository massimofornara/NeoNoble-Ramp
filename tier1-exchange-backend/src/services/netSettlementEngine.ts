import type { ClearingItem } from "./clearingQueue.js";
import { SettlementCompression } from "./settlementCompression.js";

export class NetSettlementEngine {
  constructor(private readonly compression = new SettlementCompression()) {}

  net(items: ClearingItem[]): Array<{ asset: string; netAmount: string }> {
    return this.compression.compress(items).filter((item) => Number(item.netAmount) !== 0);
  }
}
