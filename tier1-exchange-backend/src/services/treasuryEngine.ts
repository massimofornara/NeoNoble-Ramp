import type { LedgerStore } from "../core/store.js";
import { InventoryManager, type InventoryStatus } from "./inventoryManager.js";
import { Rebalancer } from "./rebalancer.js";
import { GasReserveManager, type GasReserveStatus } from "./gasReserveManager.js";
import { SettlementReserveAllocator, type SettlementReserveAllocation } from "./settlementReserveAllocator.js";
import { HedgingEngine } from "./hedgingEngine.js";

export interface TreasuryReport {
  inventory: InventoryStatus[];
  rebalancing: Array<{ asset: string; action: "hold" | "rebalance_required"; reason: string }>;
  gasReserve: GasReserveStatus;
  settlementReserves: SettlementReserveAllocation[];
  internalNetSettlement: Record<string, unknown>;
  hedging: Array<Record<string, unknown>>;
  liquidityDepletionProtection: Record<string, unknown>;
  walletSegregation: Record<string, unknown>;
  riskThresholds: Record<string, string>;
}

export class TreasuryEngine {
  private readonly inventory: InventoryManager;
  private readonly rebalancer = new Rebalancer();
  private readonly gasReserve = new GasReserveManager();
  private readonly reserveAllocator = new SettlementReserveAllocator();
  private readonly hedging = new HedgingEngine();

  constructor(ledger?: LedgerStore) {
    this.inventory = new InventoryManager(ledger);
  }

  report(assets = ["NENO", "USDT", "USDC", "WBNB", "ETH", "BTC", "WETH", "WBTC", "EUR"], onChain?: Record<string, unknown>): TreasuryReport {
    const inventory = this.hydrateOnChainInventory(assets.map((asset) => this.inventory.status(asset)), onChain);
    const settlementReserves = this.reserveAllocator.allocations(inventory);
    return {
      inventory,
      rebalancing: this.rebalancer.plan(inventory),
      gasReserve: this.gasReserve.status(),
      settlementReserves,
      internalNetSettlement: {
        enabled: true,
        mode: "clearing-book-netting-before-chain-settlement",
        compressionTarget: process.env.SETTLEMENT_COMPRESSION_TARGET ?? "max-nettable",
      },
      hedging: inventory.map((status) => this.hedging.hedge(status.asset, status.available)),
      liquidityDepletionProtection: {
        enabled: true,
        blockedAssets: settlementReserves.filter((item) => !item.allocatable).map((item) => item.asset),
        policy: "protect-buffer-plus-settlement-reserve",
      },
      walletSegregation: {
        hot: process.env.HOT_WALLET_ADDRESS ? "configured" : "not_configured",
        warm: process.env.WARM_WALLET_ADDRESS ? "configured" : "not_configured",
        cold: process.env.COLD_WALLET_ADDRESS ? "configured" : "not_configured",
        treasury: process.env.TREASURY_ADDRESS ? "configured" : "not_configured",
      },
      riskThresholds: Object.fromEntries(assets.map((asset) => [asset, process.env[`${asset}_RISK_THRESHOLD`] ?? "not_configured"])),
    };
  }

  status(onChain?: Record<string, unknown>): Record<string, unknown> {
    const report = this.report(undefined, onChain);
    const gasReserve = onChainGasReserve(report.gasReserve, onChain);
    const hydratedReport = { ...report, gasReserve };
    return {
      mode: "institutional-treasury-orchestration",
      hotWarmColdSegregation: hydratedReport.walletSegregation,
      gasReserve,
      inventoryHealthy: report.inventory.every((item) => item.healthy),
      rebalancingRequired: report.rebalancing.some((item) => item.action === "rebalance_required"),
      liquidityDepletionProtection: report.liquidityDepletionProtection,
      report: hydratedReport,
    };
  }

  exposure(onChain?: Record<string, unknown>): Record<string, unknown> {
    const inventory = this.report(undefined, onChain).inventory;
    return {
      assets: inventory.map((item) => ({
        asset: item.asset,
        available: item.available,
        reserveAllocated: item.reserveAllocated,
        buffer: item.buffer,
        utilization: item.utilization,
        depletionProtected: item.depletionProtected,
      })),
      exposureModel: "inventory-utilization-plus-reserve-allocation",
      treasuryAwareExecutionGating: true,
    };
  }

  rebalanceReport(onChain?: Record<string, unknown>): Record<string, unknown> {
    const report = this.report(undefined, onChain);
    const gasReserve = onChainGasReserve(report.gasReserve, onChain);
    return {
      generatedAt: new Date().toISOString(),
      actions: report.rebalancing,
      settlementReserves: report.settlementReserves,
      gasReserve,
      hedging: report.hedging,
      automaticRebalancer: {
        enabled: true,
        policy: "dynamic-buffer-reserve-thresholds",
      },
    };
  }

  private hydrateOnChainInventory(inventory: InventoryStatus[], onChain?: Record<string, unknown>): InventoryStatus[] {
    const balances = Array.isArray(onChain?.balances) ? (onChain.balances as Array<Record<string, unknown>>) : [];
    if (balances.length === 0) return inventory;
    return inventory.map((status) => {
      const balance = balances.find((item) => String(item.asset).toUpperCase() === status.asset.toUpperCase());
      if (!balance) return status;
      const available = String(balance.balance ?? status.available);
      const protectedMinimum = Number(status.buffer) + Number(status.reserveAllocated);
      const availableNumber = Number(available);
      return {
        ...status,
        available,
        utilization: availableNumber > 0 ? Math.min(1, protectedMinimum / availableNumber) : protectedMinimum > 0 ? 1 : 0,
        depletionProtected: availableNumber >= protectedMinimum,
        healthy: availableNumber >= protectedMinimum,
      };
    });
  }
}

function onChainGasReserve(fallback: GasReserveStatus, onChain?: Record<string, unknown>): GasReserveStatus {
  const rows = Array.isArray(onChain?.nativeGas) ? (onChain.nativeGas as Array<Record<string, unknown>>) : [];
  const primaryChain = (process.env.PRIMARY_EVM_CHAIN ?? "bsc").toLowerCase();
  const row = rows.find((item) => String(item.chainName).toLowerCase() === primaryChain) ?? rows[0];
  if (!row) return fallback;
  return {
    chain: String(row.chainName ?? fallback.chain),
    nativeAsset: String(row.asset ?? fallback.nativeAsset),
    configuredReserve: String(row.requiredReserve ?? fallback.configuredReserve),
    available: String(row.balance ?? fallback.available),
    healthy: Boolean(row.sufficient),
    escalationBudgetWei: fallback.escalationBudgetWei,
    source: "on-chain",
  };
}
