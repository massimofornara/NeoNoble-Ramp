export interface LiquidityPath {
  routeId: string;
  liquiditySource: "direct-amm" | "multi-hop-amm" | "solver-internal";
  outputAsset: OutputAsset;
  symbols: string[];
  priority: number;
}

type OutputAsset = "USDT" | "USDC" | "WBNB" | "ETH" | "BTC" | "WETH" | "WBTC";

const SUPPORTED_OUTPUTS = ["USDT", "USDC", "WBNB", "ETH", "BTC", "WETH", "WBTC"] as const;

export class LiquidityRouter {
  swapPaths(fromAsset: string, toAsset: string): LiquidityPath[] {
    const from = fromAsset.toUpperCase();
    const target = outputAsset(toAsset);
    const alternates = SUPPORTED_OUTPUTS.filter((asset) => asset !== target);
    return [
      {
        routeId: `${from}-${target}-direct`,
        liquiditySource: "direct-amm",
        outputAsset: target,
        symbols: [from, target],
        priority: 1,
      },
      ...alternates.map((intermediate, index) => ({
        routeId: `${from}-${intermediate}-${target}`,
        liquiditySource: "multi-hop-amm" as const,
        outputAsset: target,
        symbols: [from, intermediate, target],
        priority: index + 2,
      })),
    ];
  }

  bestSwapPath(fromAsset: string, toAsset: string): LiquidityPath {
    return this.swapPaths(fromAsset, toAsset).sort((left, right) => left.priority - right.priority)[0];
  }
}

function outputAsset(value: string): OutputAsset {
  const normalized = value.toUpperCase();
  if (
    normalized === "USDT" ||
    normalized === "USDC" ||
    normalized === "WBNB" ||
    normalized === "ETH" ||
    normalized === "BTC" ||
    normalized === "WETH" ||
    normalized === "WBTC"
  ) {
    return normalized;
  }
  throw new Error(`Unsupported intent output asset: ${value}`);
}
