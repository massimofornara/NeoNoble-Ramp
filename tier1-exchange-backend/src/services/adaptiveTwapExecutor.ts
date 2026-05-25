import { ExecutionAnalytics } from "./executionAnalytics.js";
import { TWAPExecutor, type TwapSlice } from "./twapExecutor.js";
import { VwapPlanner } from "./vwapPlanner.js";
import type { VenueQuote } from "./venueAdapter.js";

export class AdaptiveTwapExecutor {
  constructor(
    private readonly base = new TWAPExecutor(),
    private readonly analytics = new ExecutionAnalytics(),
    private readonly vwap = new VwapPlanner(),
  ) {}

  plan(amount: string, profile: "direct" | "medium" | "large" | "offramp", quotes: VenueQuote[]): TwapSlice[] {
    const market = this.analytics.summarize(quotes);
    const baseSlices = resizeForLiquidity(this.base.planSlices(amount, profile), amount, market.availableDepth, profile);
    const timingMultiplier = market.volatilityBps > 250 ? 1.5 : market.gasPressure === "high" ? 2 : market.gasPressure === "low" ? 0.75 : 1;
    const adjusted = baseSlices.map((slice) => ({
      ...slice,
      scheduledOffsetSeconds: Math.round(slice.scheduledOffsetSeconds * timingMultiplier),
      slippageBps: market.volatilityBps > 250 ? Math.min(5000, slice.slippageBps + 50) : slice.slippageBps,
    }));
    return this.vwap.redistribute(adjusted, quotes);
  }
}

function resizeForLiquidity(slices: TwapSlice[], amount: string, availableDepth: string, profile: "direct" | "medium" | "large" | "offramp"): TwapSlice[] {
  if (profile === "direct" || slices.length === 0) return slices;
  const amountValue = Number(amount);
  const depthValue = Number(availableDepth);
  if (!Number.isFinite(amountValue) || amountValue <= 0 || !Number.isFinite(depthValue)) return slices;
  const liquidityRatio = depthValue / amountValue;
  if (liquidityRatio >= 2) return compressSlices(slices, 2);
  if (liquidityRatio < 0.5) return expandSlices(slices, 3);
  if (liquidityRatio < 1) return expandSlices(slices, 2);
  return slices;
}

function expandSlices(slices: TwapSlice[], factor: number): TwapSlice[] {
  const interval = Number(process.env.TWAP_SLICE_INTERVAL_SECONDS ?? 60);
  return slices.flatMap((slice) =>
    splitDecimal(slice.amount, factor).map((amount, index) => ({
      ...slice,
      sliceId: `${slice.sliceId}-${index + 1}`,
      amount,
      sequence: 0,
      scheduledOffsetSeconds: slice.scheduledOffsetSeconds + index * Math.max(10, Math.round(interval / factor)),
      slippageBps: Math.max(25, Math.round(slice.slippageBps / Math.sqrt(factor))),
    })),
  ).map((slice, index) => ({ ...slice, sequence: index + 1 }));
}

function compressSlices(slices: TwapSlice[], factor: number): TwapSlice[] {
  if (slices.length <= factor) return slices;
  const compressed: TwapSlice[] = [];
  for (let index = 0; index < slices.length; index += factor) {
    const group = slices.slice(index, index + factor);
    compressed.push({
      sliceId: group[0].sliceId,
      amount: group.map((slice) => slice.amount).reduce(addDecimal, "0"),
      sequence: compressed.length + 1,
      scheduledOffsetSeconds: group[0].scheduledOffsetSeconds,
      slippageBps: Math.max(...group.map((slice) => slice.slippageBps)),
    });
  }
  return compressed;
}

function splitDecimal(amount: string, count: number): string[] {
  const units = decimalToUnits(amount, 8);
  const base = units / BigInt(count);
  const remainder = units % BigInt(count);
  return Array.from({ length: count }, (_, index) => unitsToDecimal(base + (BigInt(index) < remainder ? 1n : 0n), 8));
}

function addDecimal(left: string, right: string): string {
  return unitsToDecimal(decimalToUnits(left, 8) + decimalToUnits(right, 8), 8);
}

function decimalToUnits(value: string, scale: number): bigint {
  const normalized = String(value).trim();
  if (!/^\d+(\.\d+)?$/.test(normalized)) throw new Error(`Invalid decimal: ${value}`);
  const [whole, fraction = ""] = normalized.split(".");
  return BigInt(`${whole}${fraction.padEnd(scale, "0").slice(0, scale)}`);
}

function unitsToDecimal(units: bigint, scale: number): string {
  const divisor = 10n ** BigInt(scale);
  const whole = units / divisor;
  const fraction = (units % divisor).toString().padStart(scale, "0").replace(/0+$/, "");
  return `${whole.toString()}${fraction ? `.${fraction}` : ""}`;
}
