import { BridgeAdapter } from "./bridgeAdapter.js";
import { ChainLiquidityRegistry } from "./chainLiquidityRegistry.js";
import { CrossChainSettlement } from "./crossChainSettlement.js";

export class CrossChainRouter {
  constructor(
    private readonly registry = new ChainLiquidityRegistry(),
    private readonly bridge = new BridgeAdapter(),
    private readonly settlement = new CrossChainSettlement(),
  ) {}

  plan(asset: string, preferredChain = "bsc"): Record<string, unknown> {
    const chains = this.registry.chains().filter((chain) => chain.supportedAssets.includes(asset.toUpperCase()) && chain.rpcConfigured);
    const selected = chains.find((chain) => chain.chain === preferredChain) ?? chains[0];
    const route = selected && selected.chain !== preferredChain ? this.bridge.route(preferredChain, selected.chain) : this.bridge.route(preferredChain, preferredChain);
    return {
      selectedChain: selected?.chain ?? preferredChain,
      availableChains: chains.map((chain) => chain.chain),
      liquidityMigration: this.settlement.plan(route),
    };
  }
}
