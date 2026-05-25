import { getAddress, parseUnits } from "ethers";

export type SupportedAsset = "NENO" | "USDT" | "USDC" | "WBNB" | "ETH" | "BTC" | "WETH" | "WBTC";

export interface AssetMetadata {
  symbol: SupportedAsset;
  address: string;
  checksumAddress?: string;
  source: "env" | "internal-default" | "internal-correction";
  corrections: string[];
  decimals: number;
  chainId: number;
  chainName: string;
  native: boolean;
  wrapped: boolean;
  nativeSymbol?: string;
  liquidityVenues: string[];
  rfqEligible: boolean;
  bridgeCompatible: boolean;
  env: {
    address: string;
    decimals: string;
  };
}

const REQUIRED_ASSETS: SupportedAsset[] = ["NENO", "USDT", "USDC", "WBNB", "ETH", "BTC", "WETH", "WBTC"];
const DEFAULT_DECIMALS: Record<SupportedAsset, number> = {
  NENO: 18,
  USDT: 18,
  USDC: 18,
  WBNB: 18,
  ETH: 18,
  BTC: 8,
  WETH: 18,
  WBTC: 18,
};

const INTERNAL_ASSET_DEFAULTS: Partial<Record<SupportedAsset, { address: string; decimals: number; chainName: string }>> = {
  USDT: { address: "0x55d398326f99059fF775485246999027B3197955", decimals: 18, chainName: "bsc" },
  USDC: { address: "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d", decimals: 18, chainName: "bsc" },
  WBNB: { address: "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c", decimals: 18, chainName: "bsc" },
  ETH: { address: "native:ethereum", decimals: 18, chainName: "ethereum" },
  BTC: { address: "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599", decimals: 8, chainName: "ethereum" },
  WETH: { address: "0x2170Ed0880ac9A755fd29B2688956BD959F933F8", decimals: 18, chainName: "bsc" },
  WBTC: { address: "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c", decimals: 18, chainName: "bsc" },
};

export class AssetRegistry {
  all(): AssetMetadata[] {
    return REQUIRED_ASSETS.map((asset) => this.require(asset));
  }

  require(symbol: string): AssetMetadata {
    const asset = normalizeAsset(symbol);
    const env = addressEnv(asset);
    const resolvedAddress = resolveAddress(asset, env);
    const address = resolvedAddress.address;
    const native = isNativeAddress(address);
    const checksumAddress = native ? undefined : checksum(env, address);
    const decimalsEnv = `${asset}_DECIMALS`;
    const resolvedDecimals = decimalsFor(asset, decimalsEnv);
    const chainName = chainNameFor(asset, address);
    return {
      symbol: asset,
      address,
      checksumAddress,
      source: resolvedAddress.source === "env" && resolvedDecimals.source !== "env" ? "internal-correction" : resolvedAddress.source,
      corrections: [...resolvedAddress.corrections, ...resolvedDecimals.corrections],
      decimals: resolvedDecimals.decimals,
      chainId: chainIdFor(chainName),
      chainName,
      native,
      wrapped: asset === "WBNB" || asset === "WETH" || asset === "WBTC" || asset === "BTC" || (asset === "ETH" && !native),
      nativeSymbol:
        asset === "WBNB"
          ? "BNB"
          : asset === "WETH"
            ? "ETH"
            : asset === "ETH"
              ? "ETH"
              : asset === "BTC" || asset === "WBTC"
                ? "BTC"
                : undefined,
      liquidityVenues: listEnv(`${asset}_LIQUIDITY_VENUES`, defaultVenues(asset)),
      rfqEligible: envFlag(`${asset}_RFQ_ELIGIBLE`, asset !== "NENO"),
      bridgeCompatible: envFlag(`${asset}_BRIDGE_COMPATIBLE`, asset !== "NENO"),
      env: {
        address: env,
        decimals: decimalsEnv,
      },
    };
  }

  optional(symbol: string): AssetMetadata | undefined {
    try {
      return this.require(symbol);
    } catch {
      return undefined;
    }
  }

  address(symbol: string): string {
    const asset = this.require(symbol);
    if (!asset.checksumAddress) {
      throw new Error(`${asset.symbol} is configured as ${asset.address}; direct EVM calldata requires a wrapped routing address or RFQ/bridge route`);
    }
    return asset.checksumAddress;
  }

  decimals(symbol: string): number {
    return this.require(symbol).decimals;
  }

  parseAmount(amount: string, symbol: string): bigint {
    return parseUnits(amount, this.decimals(symbol));
  }

  assertProductionReady(): void {
    const executionMode = String(process.env.BLOCKCHAIN_EXECUTION_MODE ?? "").toLowerCase();
    if (executionMode !== "real") return;
    const errors: string[] = [];
    for (const asset of REQUIRED_ASSETS) {
      try {
        this.require(asset);
      } catch (error) {
        errors.push(error instanceof Error ? error.message : String(error));
      }
    }
    if (errors.length > 0) {
      throw new Error(`Production asset registry invariant failed: ${errors.join("; ")}`);
    }
  }

  report(): Record<string, unknown> {
    const assets = REQUIRED_ASSETS.map((asset) => {
      try {
        return { ok: true, ...this.require(asset) };
      } catch (error) {
        return {
          ok: false,
          symbol: asset,
          error: error instanceof Error ? error.message : String(error),
        };
      }
    });
    return {
      productionRequired: String(process.env.BLOCKCHAIN_EXECUTION_MODE ?? "").toLowerCase() === "real",
      assets,
      ready: assets.every((asset) => asset.ok),
    };
  }
}

export function productionAssetRegistry(): AssetRegistry {
  return new AssetRegistry();
}

function normalizeAsset(symbol: string): SupportedAsset {
  const normalized = symbol.toUpperCase();
  if (REQUIRED_ASSETS.includes(normalized as SupportedAsset)) return normalized as SupportedAsset;
  throw new Error(`Unsupported production asset: ${symbol}`);
}

function addressEnv(asset: SupportedAsset): string {
  return `${asset}_CONTRACT_ADDRESS`;
}

function resolveAddress(asset: SupportedAsset, env: string): { address: string; source: AssetMetadata["source"]; corrections: string[] } {
  const configured = process.env[env];
  const fallback = INTERNAL_ASSET_DEFAULTS[asset];
  if (!configured) {
    if (!fallback) throw new Error(`${env} is required for production asset registry`);
    return {
      address: fallback.address,
      source: "internal-default",
      corrections: [`${env} missing; using internal ${asset} production default`],
    };
  }
  if (isNativeAddress(configured)) {
    const expectedNative = fallback?.address.startsWith("native:") ? fallback.address.toLowerCase() : undefined;
    if (fallback && expectedNative && configured.toLowerCase() !== expectedNative) {
      return {
        address: fallback.address,
        source: "internal-correction",
        corrections: [`${env}=${configured} inconsistent with internal ${asset} native mapping; normalized to ${fallback.address}`],
      };
    }
    return { address: configured, source: "env", corrections: [] };
  }
  try {
    checksum(env, configured);
    return { address: configured, source: "env", corrections: [] };
  } catch {
    if (!fallback) throw new Error(`${env} must be a valid checksum-compatible EVM address`);
    return {
      address: fallback.address,
      source: "internal-correction",
      corrections: [`${env} invalid; using internal ${asset} production default`],
    };
  }
}

function checksum(env: string, value: string): string {
  try {
    return getAddress(value);
  } catch {
    throw new Error(`${env} must be a valid checksum-compatible EVM address`);
  }
}

function isNativeAddress(value: string): boolean {
  return /^native:[a-z0-9_-]+$/i.test(value);
}

function chainNameFor(asset: SupportedAsset, address: string): string {
  if (isNativeAddress(address)) return address.split(":", 2)[1].toLowerCase();
  if (asset === "BTC") return "ethereum";
  if (asset === "USDT" || asset === "USDC" || asset === "WBNB" || asset === "WETH" || asset === "WBTC" || asset === "NENO") return "bsc";
  return INTERNAL_ASSET_DEFAULTS[asset]?.chainName ?? process.env.PRIMARY_EVM_CHAIN ?? "bsc";
}

function chainIdFor(chainName: string): number {
  if (chainName === "ethereum") return Number(process.env.ETHEREUM_CHAIN_ID ?? 1);
  if (chainName === "bsc") return Number(process.env.BSC_CHAIN_ID ?? process.env.CHAIN_ID ?? 56);
  return Number(process.env[`${chainName.toUpperCase()}_CHAIN_ID`] ?? 0);
}

function decimalsFor(asset: SupportedAsset, env: string): { decimals: number; source: "env" | "internal-default" | "internal-correction"; corrections: string[] } {
  const configured = process.env[env];
  const fallback = INTERNAL_ASSET_DEFAULTS[asset]?.decimals ?? DEFAULT_DECIMALS[asset];
  if (configured === undefined) {
    return { decimals: fallback, source: "internal-default", corrections: [`${env} missing; using ${fallback}`] };
  }
  const value = Number(configured);
  if (!Number.isInteger(value) || value < 0 || value > 36) {
    return {
      decimals: fallback,
      source: "internal-correction",
      corrections: [`${env}=${configured} invalid; using ${fallback}`],
    };
  }
  return { decimals: value, source: "env", corrections: [] };
}

function listEnv(key: string, fallback: string[]): string[] {
  return (process.env[key] ?? fallback.join(","))
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

function envFlag(key: string, fallback: boolean): boolean {
  const value = process.env[key];
  if (value === undefined) return fallback;
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function defaultVenues(asset: SupportedAsset): string[] {
  if (asset === "NENO") return ["pancakeswap", "rfq", "otc", "dark-pool"];
  return ["pancakeswap", "uniswap", "1inch", "0x", "openocean", "kyberswap", "cow", "rfq", "otc", "dark-pool"];
}
