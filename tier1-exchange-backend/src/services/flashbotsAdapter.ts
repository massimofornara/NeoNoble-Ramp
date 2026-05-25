export interface PrivateRelayRequest {
  txHash?: string;
  rawTransaction?: string;
  chainId: number;
}

export class FlashbotsAdapter {
  configured(): boolean {
    return Boolean(process.env.FLASHBOTS_RELAY_URL);
  }

  route(request: PrivateRelayRequest): Record<string, unknown> | undefined {
    if (!this.configured()) return undefined;
    return {
      relay: "flashbots",
      relayUrl: process.env.FLASHBOTS_RELAY_URL,
      encrypted: true,
      chainId: request.chainId,
    };
  }
}
