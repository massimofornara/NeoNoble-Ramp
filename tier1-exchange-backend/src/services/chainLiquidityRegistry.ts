export interface ChainLiquidity {
  chain: "ethereum" | "bsc" | "arbitrum" | "base" | "polygon" | "solana";
  chainId?: number;
  rpcConfigured: boolean;
  bridgeConfigured: boolean;
  supportedAssets: string[];
}

export class ChainLiquidityRegistry {
  chains(): ChainLiquidity[] {
    return [
      chain("ethereum", 1, "ETHEREUM_RPC_URL", "ETHEREUM_BRIDGE_ADAPTER_URL"),
      chain("bsc", 56, "BSC_RPC_URL", "BSC_BRIDGE_ADAPTER_URL"),
      chain("arbitrum", 42161, "ARBITRUM_RPC_URL", "ARBITRUM_BRIDGE_ADAPTER_URL"),
      chain("base", 8453, "BASE_RPC_URL", "BASE_BRIDGE_ADAPTER_URL"),
      chain("polygon", 137, "POLYGON_RPC_URL", "POLYGON_BRIDGE_ADAPTER_URL"),
      { chain: "solana", rpcConfigured: Boolean(process.env.SOLANA_RPC_URL), bridgeConfigured: Boolean(process.env.SOLANA_BRIDGE_ADAPTER_URL), supportedAssets: assets("SOLANA") },
    ];
  }
}

function chain(chainName: ChainLiquidity["chain"], chainId: number, rpcEnv: string, bridgeEnv: string): ChainLiquidity {
  return {
    chain: chainName,
    chainId,
    rpcConfigured: Boolean(process.env[rpcEnv]),
    bridgeConfigured: Boolean(process.env[bridgeEnv]),
    supportedAssets: assets(chainName.toUpperCase()),
  };
}

function assets(prefix: string): string[] {
  return (process.env[`${prefix}_SUPPORTED_ASSETS`] ?? "USDT,USDC,WBNB,ETH,WETH,BTC,WBTC,NENO")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}
