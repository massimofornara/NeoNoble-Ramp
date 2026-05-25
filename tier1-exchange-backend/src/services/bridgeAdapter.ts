export interface BridgeRoute {
  sourceChain: string;
  targetChain: string;
  bridge: string;
  configured: boolean;
}

export class BridgeAdapter {
  route(sourceChain: string, targetChain: string): BridgeRoute {
    const key = `${sourceChain.toUpperCase()}_${targetChain.toUpperCase()}_BRIDGE_URL`;
    return {
      sourceChain,
      targetChain,
      bridge: process.env[key] ?? "not_configured",
      configured: Boolean(process.env[key]),
    };
  }
}
