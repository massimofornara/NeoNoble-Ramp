import type { LedgerStore } from "../core/store.js";

export interface InventoryStatus {
  asset: string;
  available: string;
  buffer: string;
  reserveAllocated: string;
  utilization: number;
  depletionProtected: boolean;
  healthy: boolean;
}

export class InventoryManager {
  constructor(private readonly ledger?: LedgerStore) {}

  status(asset: string): InventoryStatus {
    const balance = this.ledger?.balance("exchange-clearing")[asset] ?? process.env[`${asset.toUpperCase()}_TREASURY_BALANCE`] ?? "0";
    const buffer = process.env[`${asset.toUpperCase()}_LIQUIDITY_BUFFER`] ?? "0";
    const reserveAllocated = process.env[`${asset.toUpperCase()}_SETTLEMENT_RESERVE`] ?? "0";
    const available = Number(balance);
    const protectedMinimum = Number(buffer) + Number(reserveAllocated);
    return {
      asset,
      available: balance,
      buffer,
      reserveAllocated,
      utilization: available > 0 ? Math.min(1, protectedMinimum / available) : protectedMinimum > 0 ? 1 : 0,
      depletionProtected: available >= protectedMinimum,
      healthy: available >= protectedMinimum,
    };
  }
}
