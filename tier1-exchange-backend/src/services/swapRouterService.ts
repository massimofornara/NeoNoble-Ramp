import { Interface, JsonRpcProvider, parseUnits } from "ethers";
import type { TreasuryTransactionRequest } from "./treasurySigner.js";
import type { ValuationMetadata } from "./valuationService.js";
import { productionAssetRegistry } from "./assetRegistry.js";

const PANCAKE_V2_ROUTER_ABI = [
  "function swapExactTokensForTokens(uint256 amountIn,uint256 amountOutMin,address[] path,address to,uint256 deadline) returns (uint256[] amounts)",
  "function getAmountsOut(uint256 amountIn,address[] path) view returns (uint256[] amounts)",
];
const ERC20_ABI = ["function approve(address spender,uint256 amount) returns (bool)"];

export interface SwapExecutionPlan {
  preSettlementTransactions: TreasuryTransactionRequest[];
  transaction: TreasuryTransactionRequest;
  router: string;
  path: string[];
  routeId: string;
  liquiditySource: string;
  amountInRaw: string;
  amountOutMinRaw: string;
  slippageBps: number;
  deadline: number;
  approvalMode: "exact" | "preapproved";
  calldataKind: "pancake-v2-swapExactTokensForTokens";
}

export interface SwapBuildInput {
  fromAsset: string;
  toAsset: string;
  amount: string;
  valuation: ValuationMetadata;
  recipient?: string;
  slippageBps?: number;
  deadlineSeconds?: number;
  route?: SwapRouteCandidate;
}

export interface SwapRouteCandidate {
  routeId: string;
  liquiditySource: string;
  routerAddress: string;
  path: string[];
}

export interface SwapQuote {
  routeId: string;
  liquiditySource: string;
  quotedOutRaw: string;
  amountOutMinRaw: string;
  valid: boolean;
}

export class SwapRouterService {
  private readonly iface = new Interface(PANCAKE_V2_ROUTER_ABI);

  routeCandidates(fromAsset: string, toAsset: string): SwapRouteCandidate[] {
    const tokenIn = tokenAddress(routeSymbol(fromAsset));
    const tokenOut = tokenAddress(routeSymbol(toAsset));
    const primary = {
      routeId: "pancake-v2-primary",
      liquiditySource: "pancake-v2",
      routerAddress: requiredAddress("BSC_SWAP_ROUTER_ADDRESS", process.env.BSC_SWAP_ROUTER_ADDRESS),
      path: [tokenIn, tokenOut],
    };
    const multiHop = ["USDT", "USDC", "WBNB"]
      .filter((symbol) => symbol !== fromAsset.toUpperCase() && symbol !== toAsset.toUpperCase())
      .map((symbol) => optionalTokenAddress(symbol))
      .filter((address): address is string => Boolean(address))
      .map((intermediate, index) => ({
        routeId: `pancake-v2-multihop-${index + 1}`,
        liquiditySource: "pancake-v2-multihop",
        routerAddress: primary.routerAddress,
        path: [tokenIn, intermediate, tokenOut],
      }));
    const secondaryRouter = process.env.BSC_SECONDARY_SWAP_ROUTER_ADDRESS;
    const secondaryPath = process.env.BSC_SECONDARY_SWAP_PATH;
    if (!secondaryRouter || !secondaryPath) return [primary, ...multiHop];
    return [
      primary,
      ...multiHop,
      {
        routeId: "secondary-amm-configured",
        liquiditySource: "secondary-amm",
        routerAddress: requiredAddress("BSC_SECONDARY_SWAP_ROUTER_ADDRESS", secondaryRouter),
        path: parsePath(secondaryPath, routeSymbol(fromAsset), routeSymbol(toAsset)),
      },
    ];
  }

  buildSwap(input: SwapBuildInput): SwapExecutionPlan {
    const route = input.route ?? this.routeCandidates(input.fromAsset, input.toAsset)[0];
    const router = requiredAddress(`${route.routeId} router`, route.routerAddress);
    const treasury = requiredAddress("TREASURY_ADDRESS", process.env.TREASURY_ADDRESS);
    const recipient = requiredAddress("swap recipient", input.recipient ?? process.env.SWAP_RECIPIENT_ADDRESS ?? treasury);
    const routeInAsset = routeSymbol(input.fromAsset);
    const routeOutAsset = routeSymbol(input.toAsset);
    const tokenIn = tokenAddress(routeInAsset);
    const tokenOut = tokenAddress(routeOutAsset);
    if (route.path[0].toLowerCase() !== tokenIn.toLowerCase() || route.path.at(-1)?.toLowerCase() !== tokenOut.toLowerCase()) {
      throw new Error(`Swap route ${route.routeId} must start with ${input.fromAsset} and end with ${input.toAsset}`);
    }
    const amountInRaw = parseTokenAmount(input.amount, routeInAsset).toString();
    const expectedOutRaw = parseTokenAmount(input.valuation.targetAmount, routeOutAsset);
    const slippageBps = Number(input.slippageBps ?? process.env.SWAP_SLIPPAGE_BPS ?? 50);
    if (!Number.isInteger(slippageBps) || slippageBps < 0 || slippageBps > 5000) {
      throw new Error("SWAP_SLIPPAGE_BPS must be an integer between 0 and 5000");
    }
    const amountOutMinRaw = ((expectedOutRaw * BigInt(10_000 - slippageBps)) / 10_000n).toString();
    const deadline = Math.floor(Date.now() / 1000) + Number(input.deadlineSeconds ?? process.env.SWAP_DEADLINE_SECONDS ?? 600);
    const data = this.iface.encodeFunctionData("swapExactTokensForTokens", [amountInRaw, amountOutMinRaw, route.path, recipient, deadline]);
    const approvalMode = String(process.env.SWAP_APPROVAL_MODE ?? "exact").toLowerCase() === "preapproved" ? "preapproved" : "exact";
    const approvalIface = new Interface(ERC20_ABI);
    return {
      preSettlementTransactions:
        approvalMode === "exact"
          ? [
              {
                to: tokenIn,
                data: approvalIface.encodeFunctionData("approve", [router, amountInRaw]),
                valueWei: "0",
              },
            ]
          : [],
      transaction: {
        to: router,
        data,
        valueWei: "0",
      },
      router,
      path: route.path,
      routeId: route.routeId,
      liquiditySource: route.liquiditySource,
      amountInRaw,
      amountOutMinRaw,
      slippageBps,
      deadline,
      approvalMode,
      calldataKind: "pancake-v2-swapExactTokensForTokens",
    };
  }

  async assertExecutableQuote(plan: SwapExecutionPlan): Promise<SwapQuote> {
    const quote = await this.quote(plan);
    if (!quote.valid) {
      throw new Error(
        `${plan.liquiditySource} quote below protected minOut: quotedOutRaw=${quote.quotedOutRaw} amountOutMinRaw=${quote.amountOutMinRaw} slippageBps=${plan.slippageBps} routeId=${plan.routeId}`,
      );
    }
    return quote;
  }

  async quote(plan: SwapExecutionPlan): Promise<SwapQuote> {
    const rpcUrl = process.env.BSC_RPC_URL;
    if (!rpcUrl) throw new Error("BSC_RPC_URL is required to validate PancakeSwap quote before broadcast");
    const provider = new JsonRpcProvider(rpcUrl, Number(process.env.BSC_CHAIN_ID ?? process.env.CHAIN_ID ?? 56));
    const data = this.iface.encodeFunctionData("getAmountsOut", [plan.amountInRaw, plan.path]);
    let decoded: unknown;
    try {
      const raw = await provider.call({ to: plan.router, data });
      decoded = this.iface.decodeFunctionResult("getAmountsOut", raw)[0];
    } catch (error) {
      throw new Error(`PancakeSwap quote unavailable for path ${plan.path.join(" -> ")}: ${error instanceof Error ? error.message : String(error)}`);
    }
    const amounts = Array.isArray(decoded) ? decoded.map((value) => BigInt(value.toString())) : [];
    const quotedOut = amounts.at(-1);
    if (quotedOut === undefined) {
      throw new Error("PancakeSwap quote did not return an output amount");
    }
    const minOut = BigInt(plan.amountOutMinRaw);
    return {
      routeId: plan.routeId,
      liquiditySource: plan.liquiditySource,
      quotedOutRaw: quotedOut.toString(),
      amountOutMinRaw: minOut.toString(),
      valid: quotedOut >= minOut,
    };
  }
}

function parsePath(value: string, fromAsset: string, toAsset: string): string[] {
  const parts = value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
  if (parts.length < 2) {
    throw new Error("BSC_SECONDARY_SWAP_PATH must contain at least token-in and token-out");
  }
  return parts.map((part) => (/^0x[a-fA-F0-9]{40}$/.test(part) ? part : tokenAddress(part)));
}

function routeSymbol(symbol: string): string {
  const normalized = symbol.toUpperCase();
  if (normalized === "ETH") return process.env.ETH_ROUTING_SYMBOL ?? "WETH";
  if (normalized === "BTC") return process.env.BTC_ROUTING_SYMBOL ?? "WBTC";
  return normalized;
}

function tokenAddress(symbol: string): string {
  return productionAssetRegistry().address(symbol);
}

function optionalTokenAddress(symbol: string): string | undefined {
  return productionAssetRegistry().optional(symbol)?.checksumAddress;
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
