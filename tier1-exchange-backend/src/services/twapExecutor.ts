export interface TwapSlice {
  sliceId: string;
  amount: string;
  sequence: number;
  scheduledOffsetSeconds: number;
  slippageBps: number;
}

export class TWAPExecutor {
  planSlices(amount: string, profile: "direct" | "medium" | "large" | "offramp"): TwapSlice[] {
    const count = sliceCount(amount, profile);
    const interval = Number(process.env.TWAP_SLICE_INTERVAL_SECONDS ?? 60);
    const slippage = Number(process.env.TWAP_SLIPPAGE_BPS ?? process.env.SWAP_SLIPPAGE_BPS ?? 75);
    const pieces = splitDecimal(amount, count);
    return pieces.map((piece, index) => ({
      sliceId: `slice-${String(index + 1).padStart(3, "0")}`,
      amount: piece,
      sequence: index + 1,
      scheduledOffsetSeconds: index * interval,
      slippageBps: slippage,
    }));
  }
}

function sliceCount(amount: string, profile: "direct" | "medium" | "large" | "offramp"): number {
  const value = Number(amount);
  if (!Number.isFinite(value) || value <= 0) throw new Error(`Invalid TWAP amount: ${amount}`);
  if (profile === "direct") return 1;
  if (profile === "offramp") return Math.max(1, Math.min(5, Math.ceil(value / 100)));
  if (profile === "medium") {
    const targetSlice = Number(process.env.TWAP_MEDIUM_TARGET_SLICE_NENO ?? 500);
    const maxSlices = Number(process.env.TWAP_MEDIUM_MAX_SLICES ?? 20);
    return Math.max(2, Math.min(maxSlices, Math.ceil(value / targetSlice)));
  }
  const targetSlice = Number(process.env.TWAP_LARGE_TARGET_SLICE_NENO ?? 1_000);
  const maxSlices = Number(process.env.TWAP_LARGE_MAX_SLICES ?? 120);
  return Math.max(10, Math.min(maxSlices, Math.ceil(value / targetSlice)));
}

function splitDecimal(amount: string, count: number): string[] {
  const scale = 8n;
  const units = decimalToUnits(amount, Number(scale));
  const base = units / BigInt(count);
  const remainder = units % BigInt(count);
  return Array.from({ length: count }, (_, index) => {
    const extra = BigInt(index) < remainder ? 1n : 0n;
    return unitsToDecimal(base + extra, Number(scale));
  });
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
