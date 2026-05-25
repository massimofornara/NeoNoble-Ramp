import { Contract, JsonRpcProvider, formatUnits } from "ethers";
import { AssetRegistry, type AssetMetadata } from "./assetRegistry.js";

const ERC20_ABI = ["function balanceOf(address account) view returns (uint256)"];

export interface OnChainTreasuryBalance {
  asset: string;
  chainName: string;
  chainId: number;
  address: string;
  balance: string;
  requiredForBatch: string;
  sufficientForBatch: boolean;
}

export class TreasuryOnChainService {
  constructor(private readonly registry = new AssetRegistry()) {}

  async balances(treasury = process.env.TREASURY_ADDRESS ?? ""): Promise<Record<string, unknown>> {
    if (!/^0x[a-fA-F0-9]{40}$/.test(treasury)) throw new Error("TREASURY_ADDRESS is required for on-chain treasury validation");
    const assets = this.registry.all();
    const balances = await Promise.all(assets.map((asset) => this.balance(asset, treasury)));
    const nativeGas = await this.nativeGasBalances(treasury);
    return {
      treasury,
      balances,
      nativeGas,
      fundingSufficientForConfiguredBatch:
        balances.every((balance) => balance.sufficientForBatch) &&
        nativeGas.every((balance) => Number(balance.balance) >= Number(balance.requiredReserve)),
    };
  }

  private async balance(asset: AssetMetadata, treasury: string): Promise<OnChainTreasuryBalance> {
    if (asset.native) {
      const provider = providerFor(asset.chainName);
      const balance = formatUnits(await provider.getBalance(treasury), asset.decimals);
      const requiredForBatch = requiredBalance(asset.symbol);
      return {
        asset: asset.symbol,
        chainName: asset.chainName,
        chainId: asset.chainId,
        address: asset.address,
        balance,
        requiredForBatch,
        sufficientForBatch: Number(balance) >= Number(requiredForBatch),
      };
    }
    if (!asset.checksumAddress) throw new Error(`${asset.symbol} has no EVM balanceOf address`);
    const provider = providerFor(asset.chainName);
    const contract = new Contract(asset.checksumAddress, ERC20_ABI, provider);
    const balance = formatUnits((await contract.balanceOf(treasury)) as bigint, asset.decimals);
    const requiredForBatch = requiredBalance(asset.symbol);
    return {
      asset: asset.symbol,
      chainName: asset.chainName,
      chainId: asset.chainId,
      address: asset.checksumAddress,
      balance,
      requiredForBatch,
      sufficientForBatch: Number(balance) >= Number(requiredForBatch),
    };
  }

  private async nativeGasBalances(treasury: string): Promise<Array<Record<string, unknown>>> {
    const chains = [
      { chainName: "bsc", asset: "BNB", reserve: process.env.BSC_GAS_RESERVE ?? process.env.GAS_RESERVE_NATIVE ?? "0" },
      { chainName: "ethereum", asset: "ETH", reserve: process.env.ETHEREUM_GAS_RESERVE ?? "0" },
    ];
    const configured = chains.filter((chain) => rpcUrlFor(chain.chainName));
    return Promise.all(
      configured.map(async (chain) => {
        const provider = providerFor(chain.chainName);
        const balance = formatUnits(await provider.getBalance(treasury), 18);
        return {
          chainName: chain.chainName,
          asset: chain.asset,
          balance,
          requiredReserve: chain.reserve,
          sufficient: Number(balance) >= Number(chain.reserve),
        };
      }),
    );
  }
}

function providerFor(chainName: string): JsonRpcProvider {
  const rpcUrl = rpcUrlFor(chainName);
  if (!rpcUrl) throw new Error(`${chainName.toUpperCase()} RPC URL is required for on-chain treasury validation`);
  const chainId = chainName === "ethereum" ? Number(process.env.ETHEREUM_CHAIN_ID ?? 1) : Number(process.env.BSC_CHAIN_ID ?? 56);
  return new JsonRpcProvider(rpcUrl, chainId);
}

function rpcUrlFor(chainName: string): string | undefined {
  if (chainName === "ethereum") return process.env.ETHEREUM_RPC_URL;
  if (chainName === "bsc") return process.env.BSC_RPC_URL;
  return process.env[`${chainName.toUpperCase()}_RPC_URL`];
}

function requiredBalance(asset: string): string {
  if (asset === "NENO") return process.env.PRODUCTION_BATCH_REQUIRED_NENO ?? "1969850";
  return process.env[`${asset}_TREASURY_REQUIRED_BALANCE`] ?? "0";
}
