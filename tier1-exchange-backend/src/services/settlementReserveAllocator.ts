import type { InventoryStatus } from "./inventoryManager.js";

export interface SettlementReserveAllocation {
  asset: string;
  reserve: string;
  availableAfterReserve: string;
  allocatable: boolean;
}

export class SettlementReserveAllocator {
  allocations(inventory: InventoryStatus[]): SettlementReserveAllocation[] {
    return inventory.map((status) => {
      const available = Number(status.available);
      const reserve = Number(status.reserveAllocated);
      return {
        asset: status.asset,
        reserve: status.reserveAllocated,
        availableAfterReserve: String(Math.max(0, available - reserve)),
        allocatable: available > reserve && status.healthy,
      };
    });
  }
}
