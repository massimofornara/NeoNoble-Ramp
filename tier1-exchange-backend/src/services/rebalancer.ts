import type { InventoryStatus } from "./inventoryManager.js";

export class Rebalancer {
  plan(statuses: InventoryStatus[]): Array<{ asset: string; action: "hold" | "rebalance_required"; reason: string }> {
    return statuses.map((status) => ({
      asset: status.asset,
      action: status.healthy ? "hold" : "rebalance_required",
      reason: status.healthy ? "buffer_satisfied" : `available ${status.available} below buffer ${status.buffer}`,
    }));
  }
}
