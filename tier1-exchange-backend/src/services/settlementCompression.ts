import type { ClearingItem } from "./clearingQueue.js";

export class SettlementCompression {
  compress(items: ClearingItem[]): Array<{ asset: string; netAmount: string }> {
    const totals = new Map<string, number>();
    for (const item of items) {
      const signed = item.direction === "in" ? Number(item.amount) : -Number(item.amount);
      totals.set(item.asset, (totals.get(item.asset) ?? 0) + signed);
    }
    return [...totals.entries()].map(([asset, value]) => ({ asset, netAmount: String(value) }));
  }
}
