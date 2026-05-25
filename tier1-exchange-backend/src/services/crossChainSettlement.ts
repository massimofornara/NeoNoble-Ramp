import type { BridgeRoute } from "./bridgeAdapter.js";

export class CrossChainSettlement {
  plan(route: BridgeRoute): Record<string, unknown> {
    return {
      route,
      settlementMode: route.configured ? "bridge-aware" : "same-chain-required",
      requiresBridgeProof: route.configured,
    };
  }
}
