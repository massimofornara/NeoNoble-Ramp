export interface GasReserveStatus {
  chain: string;
  nativeAsset: string;
  configuredReserve: string;
  available: string;
  healthy: boolean;
  escalationBudgetWei: string;
  source?: "env" | "on-chain";
}

export class GasReserveManager {
  status(chain = process.env.PRIMARY_EVM_CHAIN ?? "bsc"): GasReserveStatus {
    const normalized = chain.toUpperCase();
    const nativeAsset = normalized === "BSC" ? "BNB" : normalized === "ETHEREUM" ? "ETH" : `${normalized}_NATIVE`;
    const configuredReserve = process.env[`${normalized}_GAS_RESERVE`] ?? process.env.GAS_RESERVE_NATIVE ?? "0";
    const available = process.env[`${normalized}_GAS_AVAILABLE`] ?? process.env.GAS_AVAILABLE_NATIVE ?? "0";
    return {
      chain: chain.toLowerCase(),
      nativeAsset,
      configuredReserve,
      available,
      healthy: Number(available) >= Number(configuredReserve),
      escalationBudgetWei: process.env[`${normalized}_TX_ESCALATION_BUDGET_WEI`] ?? process.env.TX_ESCALATION_BUDGET_WEI ?? "0",
      source: "env",
    };
  }
}
