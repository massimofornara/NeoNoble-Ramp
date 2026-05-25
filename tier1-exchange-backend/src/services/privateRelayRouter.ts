import { FlashbotsAdapter, type PrivateRelayRequest } from "./flashbotsAdapter.js";

export class PrivateRelayRouter {
  constructor(private readonly flashbots = new FlashbotsAdapter()) {}

  select(request: PrivateRelayRequest): Record<string, unknown> {
    const flashbots = this.flashbots.route(request);
    if (flashbots) return { priority: 1, ...flashbots };
    if (process.env.MEV_BLOCKER_RELAY_URL) {
      return {
        priority: 2,
        relay: "mev-blocker",
        relayUrl: process.env.MEV_BLOCKER_RELAY_URL,
        encrypted: true,
        chainId: request.chainId,
      };
    }
    return {
      priority: 3,
      relay: "protected-public-mempool",
      antiSandwich: true,
      chainId: request.chainId,
    };
  }
}
