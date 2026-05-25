import { Interface, JsonRpcProvider, formatUnits, parseUnits } from "ethers";
import { productionAssetRegistry } from "./assetRegistry.js";

export type VenueName = "pancakeswap" | "uniswap" | "1inch" | "0x" | "openocean" | "kyberswap" | "cow" | "rfq" | "dwf";

export interface QuoteRequest {
  intentId?: string;
  chainId: number;
  fromAsset: string;
  toAsset: string;
  amount: string;
  expectedToAmount?: string;
  slippageBps?: number;
}

export interface VenueQuote {
  quoteId: string;
  venue: VenueName;
  liquiditySource: string;
  route: string[];
  inputAmount: string;
  outputAmount: string;
  effectivePrice: string;
  gasCostUsd: string;
  slippageBps: number;
  liquidityDepth: string;
  failureProbability: number;
  expiresAt: string;
  privateSettlement: boolean;
  metadata: Record<string, unknown>;
}

export interface ExecutionVenueAdapter {
  readonly venue: VenueName;
  quote(request: QuoteRequest): Promise<VenueQuote | undefined>;
}

const V2_ROUTER_ABI = ["function getAmountsOut(uint256 amountIn,address[] path) view returns (uint256[] amounts)"];

export class V2AmmVenueAdapter implements ExecutionVenueAdapter {
  private readonly iface = new Interface(V2_ROUTER_ABI);

  constructor(
    readonly venue: VenueName,
    private readonly routerEnv: string,
    private readonly rpcEnv: string,
    private readonly liquiditySource: string,
  ) {}

  async quote(request: QuoteRequest): Promise<VenueQuote | undefined> {
    const router = process.env[this.routerEnv];
    const rpcUrl = process.env[this.rpcEnv];
    if (!router || !rpcUrl) return undefined;
    const path = tokenPath(request.fromAsset, request.toAsset, request.chainId);
    const provider = new JsonRpcProvider(rpcUrl, request.chainId);
    const amountInRaw = parseUnits(request.amount, tokenDecimals(request.fromAsset, request.chainId)).toString();
    const data = this.iface.encodeFunctionData("getAmountsOut", [amountInRaw, path]);
    const raw = await provider.call({ to: router, data });
    const decoded = this.iface.decodeFunctionResult("getAmountsOut", raw)[0] as Array<{ toString(): string }>;
    const outputRaw = decoded.at(-1)?.toString();
    if (!outputRaw) return undefined;
    const outputAmount = formatUnits(outputRaw, tokenDecimals(request.toAsset, request.chainId));
    const gasCostUsd = String(process.env[`${this.venue.toUpperCase()}_GAS_COST_USD`] ?? "0");
    return normalizeQuote({
      request,
      venue: this.venue,
      liquiditySource: this.liquiditySource,
      route: [request.fromAsset.toUpperCase(), request.toAsset.toUpperCase()],
      outputAmount,
      gasCostUsd,
      failureProbability: Number(process.env[`${this.venue.toUpperCase()}_FAILURE_PROBABILITY`] ?? "0.02"),
      privateSettlement: false,
      metadata: {
        router,
        path,
        outputRaw,
      },
    });
  }
}

export class ExternalVenueAdapter implements ExecutionVenueAdapter {
  constructor(
    readonly venue: VenueName,
    private readonly endpointEnv: string,
    private readonly apiKeyEnv?: string,
  ) {}

  async quote(request: QuoteRequest): Promise<VenueQuote | undefined> {
    const endpoint = process.env[this.endpointEnv];
    if (!endpoint) return undefined;
    const headers: Record<string, string> = { "content-type": "application/json" };
    const apiKey = this.apiKeyEnv ? process.env[this.apiKeyEnv] : undefined;
    if (apiKey) headers.authorization = `Bearer ${apiKey}`;
    const response = await fetch(endpoint, {
      method: "POST",
      headers,
      body: JSON.stringify(request),
    });
    if (!response.ok) {
      throw new Error(`${this.venue} quote endpoint failed with ${response.status}`);
    }
    const body = (await response.json()) as Record<string, unknown>;
    const outputAmount = stringField(body, "outputAmount") ?? stringField(body, "buyAmount") ?? stringField(body, "toAmount");
    if (!outputAmount) return undefined;
    return normalizeQuote({
      request,
      venue: this.venue,
      liquiditySource: `${this.venue}-api`,
      route: Array.isArray(body.route) ? body.route.map(String) : [request.fromAsset, request.toAsset],
      outputAmount,
      gasCostUsd: stringField(body, "gasCostUsd") ?? "0",
      failureProbability: numberField(body, "failureProbability") ?? 0.05,
      privateSettlement: Boolean(body.privateSettlement),
      metadata: {
        ...body,
        executable: executableTransactionPresent(body),
      },
    });
  }
}

function normalizeQuote(input: {
  request: QuoteRequest;
  venue: VenueName;
  liquiditySource: string;
  route: string[];
  outputAmount: string;
  gasCostUsd: string;
  failureProbability: number;
  privateSettlement: boolean;
  metadata: Record<string, unknown>;
}): VenueQuote {
  const expected = Number(input.request.expectedToAmount ?? "0");
  const output = Number(input.outputAmount);
  const referenceSlippageBps = expected > 0 ? Math.max(0, Math.round(((expected - output) / expected) * 10_000)) : 0;
  const providerSlippageBps = numberField(input.metadata, "providerSlippageBps") ?? input.request.slippageBps ?? 0;
  const effectivePrice = Number(input.request.amount) > 0 ? String(output / Number(input.request.amount)) : "0";
  return {
    quoteId: `${input.venue}:${Date.now()}:${Math.random().toString(16).slice(2)}`,
    venue: input.venue,
    liquiditySource: input.liquiditySource,
    route: input.route,
    inputAmount: input.request.amount,
    outputAmount: input.outputAmount,
    effectivePrice,
    gasCostUsd: input.gasCostUsd,
    slippageBps: Math.max(0, providerSlippageBps),
    liquidityDepth: input.outputAmount,
    failureProbability: Math.min(1, Math.max(0, input.failureProbability)),
    expiresAt: new Date(Date.now() + Number(process.env.QUOTE_TTL_MS ?? 20_000)).toISOString(),
    privateSettlement: input.privateSettlement,
    metadata: {
      ...input.metadata,
      quoteReceivedAt: new Date().toISOString(),
      referenceValuationAmount: input.request.expectedToAmount,
      referenceSlippageBps,
    },
  };
}

function tokenPath(fromAsset: string, toAsset: string, chainId: number): string[] {
  return [tokenAddress(fromAsset, chainId), tokenAddress(toAsset, chainId)];
}

function tokenAddress(symbol: string, chainId: number): string {
  return productionAssetRegistry().address(routableAsset(symbol, chainId));
}

function tokenDecimals(symbol: string, chainId: number): number {
  return productionAssetRegistry().decimals(routableAsset(symbol, chainId));
}

function routableAsset(symbol: string, chainId: number): string {
  const normalized = symbol.toUpperCase();
  if (chainId === 56 && normalized === "ETH") return "WETH";
  if (chainId === 56 && normalized === "BTC") return "WBTC";
  return normalized;
}

function stringField(value: Record<string, unknown>, key: string): string | undefined {
  const field = value[key];
  return field === undefined || field === null ? undefined : String(field);
}

function numberField(value: Record<string, unknown>, key: string): number | undefined {
  const field = Number(value[key]);
  return Number.isFinite(field) ? field : undefined;
}

function executableTransactionPresent(body: Record<string, unknown>): boolean {
  const transaction = firstRecord(body.transaction, body.tx, body.settlementTransaction, asRecord(body.execution).transaction, asRecord(body.execution).tx);
  return Boolean(
    transaction &&
      /^0x[a-fA-F0-9]{40}$/.test(String(transaction.to ?? transaction.target ?? "")) &&
      /^0x([a-fA-F0-9]{2})*$/.test(String(transaction.data ?? transaction.calldata ?? "")),
  );
}

function firstRecord(...values: unknown[]): Record<string, unknown> | undefined {
  return values.find((value): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value));
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}
