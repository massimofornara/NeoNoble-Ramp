import { Interface, JsonRpcProvider, parseUnits } from "ethers";
import type { TreasuryTransactionRequest } from "./treasurySigner.js";
import type { ValuationMetadata } from "./valuationService.js";
import { productionAssetRegistry } from "./assetRegistry.js";

const ERC20_ABI = ["function transfer(address to,uint256 amount) returns (bool)"];

export interface OfframpExecutionPlan {
  transaction: TreasuryTransactionRequest;
  custodyAddress: string;
  tokenAddress: string;
  amountRaw: string;
  fiatCurrency: string;
  fiatValue: string;
  calldataKind: "erc20-transfer-to-offramp-custody";
}

export interface OfframpBuildInput {
  fromAsset: string;
  amount: string;
  fiatCurrency: string;
  valuation: ValuationMetadata;
  custodyAddress?: string;
}

export class OfframpRouterService {
  buildOfframp(input: OfframpBuildInput): OfframpExecutionPlan {
    const custodyAddress = requiredAddress("OFFRAMP_CUSTODY_ADDRESS", input.custodyAddress ?? process.env.OFFRAMP_CUSTODY_ADDRESS);
    const token = tokenAddress(input.fromAsset);
    const amountRaw = parseTokenAmount(input.amount, input.fromAsset).toString();
    const iface = new Interface(ERC20_ABI);
    const data = iface.encodeFunctionData("transfer", [custodyAddress, amountRaw]);
    return {
      transaction: {
        to: token,
        data,
        valueWei: "0",
      },
      custodyAddress,
      tokenAddress: token,
      amountRaw,
      fiatCurrency: input.fiatCurrency,
      fiatValue: input.valuation.targetAmount,
      calldataKind: "erc20-transfer-to-offramp-custody",
    };
  }

  async assertExecutablePreflight(plan: OfframpExecutionPlan): Promise<void> {
    const rpcUrl = process.env.BSC_RPC_URL;
    if (!rpcUrl) throw new Error("BSC_RPC_URL is required for offramp preflight simulation");
    const treasury = requiredAddress("TREASURY_ADDRESS", process.env.TREASURY_ADDRESS);
    const provider = new JsonRpcProvider(rpcUrl, Number(process.env.BSC_CHAIN_ID ?? process.env.CHAIN_ID ?? 56));
    const request = {
      from: treasury,
      to: plan.transaction.to,
      data: plan.transaction.data ?? "0x",
      value: BigInt(plan.transaction.valueWei ?? "0"),
    };
    try {
      await provider.call(request);
      await provider.estimateGas(request);
    } catch (error) {
      throw new Error(`OFFRAMP_PREFLIGHT_FAILED: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
}

function tokenAddress(symbol: string): string {
  return productionAssetRegistry().address(symbol);
}

function parseTokenAmount(amount: string, symbol: string): bigint {
  return parseUnits(amount, productionAssetRegistry().decimals(symbol));
}

function requiredAddress(name: string, value: string | undefined): string {
  if (!value || !/^0x[a-fA-F0-9]{40}$/.test(value)) {
    throw new Error(`${name} must be configured as an EVM address`);
  }
  return value;
}
