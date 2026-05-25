import { formatUnits, parseUnits } from "ethers";
import { productionAssetRegistry } from "./assetRegistry.js";
import type { QuoteRequest, VenueName, VenueQuote } from "./venueAdapter.js";

export interface DexQuoteInput {
  request: QuoteRequest;
  venue: VenueName;
  liquiditySource: string;
  quoteId?: string;
  route?: string[];
  outputAmount?: string;
  outputAmountRaw?: string;
  gasCostUsd?: string;
  failureProbability?: number;
  privateSettlement?: boolean;
  expiresAt?: string;
  metadata: Record<string, unknown>;
}

export function buildDexQuote(input: DexQuoteInput): VenueQuote | undefined {
  const outputAmount = input.outputAmount ?? formatRawOutput(input.outputAmountRaw, input.request.toAsset, input.request.chainId);
  if (!outputAmount) return undefined;
  const expected = Number(input.request.expectedToAmount ?? "0");
  const output = Number(outputAmount);
  const referenceSlippageBps = expected > 0 ? Math.max(0, Math.round(((expected - output) / expected) * 10_000)) : 0;
  const providerSlippageBps = numberField(input.metadata, "providerSlippageBps") ?? input.request.slippageBps ?? 0;
  const inputAmount = Number(input.request.amount);
  return {
    quoteId: input.quoteId ?? `${input.venue}:${input.liquiditySource}:${Date.now()}:${Math.random().toString(16).slice(2)}`,
    venue: input.venue,
    liquiditySource: input.liquiditySource,
    route: input.route ?? [input.request.fromAsset.toUpperCase(), input.request.toAsset.toUpperCase()],
    inputAmount: input.request.amount,
    outputAmount,
    effectivePrice: inputAmount > 0 ? String(output / inputAmount) : "0",
    gasCostUsd: input.gasCostUsd ?? "0",
    slippageBps: Math.max(0, providerSlippageBps),
    liquidityDepth: outputAmount,
    failureProbability: Math.min(1, Math.max(0, input.failureProbability ?? 0.05)),
    expiresAt: input.expiresAt ?? new Date(Date.now() + Number(process.env.QUOTE_TTL_MS ?? 20_000)).toISOString(),
    privateSettlement: Boolean(input.privateSettlement),
    metadata: {
      ...input.metadata,
      quoteReceivedAt: new Date().toISOString(),
      referenceValuationAmount: input.request.expectedToAmount,
      referenceSlippageBps,
    },
  };
}

export function assetAddress(symbol: string, chainId: number): string {
  return productionAssetRegistry().address(routableAsset(symbol, chainId));
}

export function assetDecimals(symbol: string, chainId: number): number {
  return productionAssetRegistry().decimals(routableAsset(symbol, chainId));
}

export function rawInputAmount(request: QuoteRequest): string {
  return parseUnits(request.amount, assetDecimals(request.fromAsset, request.chainId)).toString();
}

export function routableAsset(symbol: string, chainId: number): string {
  const normalized = symbol.toUpperCase();
  if (chainId === 56 && normalized === "ETH") return "WETH";
  if (chainId === 56 && normalized === "BTC") return "WBTC";
  return normalized;
}

export function stringField(value: Record<string, unknown>, ...keys: string[]): string | undefined {
  for (const key of keys) {
    const field = value[key];
    if (field !== undefined && field !== null && field !== "") return String(field);
  }
  return undefined;
}

export function numberField(value: Record<string, unknown>, key: string): number | undefined {
  const field = Number(value[key]);
  return Number.isFinite(field) ? field : undefined;
}

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

export function firstRecord(...values: unknown[]): Record<string, unknown> | undefined {
  return values.find((value): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value));
}

export function hasExecutableTransaction(value: Record<string, unknown>): boolean {
  const transaction = firstRecord(value.transaction, value.tx, value.settlementTransaction, asRecord(value.execution).transaction, asRecord(value.execution).tx);
  if (!transaction) return false;
  const to = String(transaction.to ?? transaction.target ?? "");
  const data = String(transaction.data ?? transaction.calldata ?? "");
  return /^0x[a-fA-F0-9]{40}$/.test(to) && /^0x([a-fA-F0-9]{2})*$/.test(data);
}

export function containsString(value: unknown, needle: string): boolean {
  if (typeof value === "string") return value.toLowerCase() === needle.toLowerCase() || value.toLowerCase().includes(needle.toLowerCase());
  if (Array.isArray(value)) return value.some((item) => containsString(item, needle));
  if (value && typeof value === "object") return Object.values(value as Record<string, unknown>).some((item) => containsString(item, needle));
  return false;
}

export async function fetchJson(url: URL, headers: Record<string, string>, venue: string): Promise<Record<string, unknown>> {
  const response = await fetch(url, { method: "GET", headers });
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${venue} quote endpoint failed with ${response.status}: ${safeBody(text)}`);
  }
  if (!text) return {};
  const parsed = JSON.parse(text) as unknown;
  return asRecord(parsed);
}

export function appendQuery(url: URL, values: Record<string, string | number | undefined>): URL {
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
  }
  return url;
}

function formatRawOutput(raw: string | undefined, symbol: string, chainId: number): string | undefined {
  if (!raw) return undefined;
  if (!/^\d+$/.test(raw)) return raw;
  return formatUnits(raw, assetDecimals(symbol, chainId));
}

function safeBody(text: string): string {
  return text.replace(/[A-Za-z0-9_-]{24,}/g, "<redacted>").slice(0, 500);
}
