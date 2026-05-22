const SCALE = 18n;
const FACTOR = 10n ** SCALE;

export function toAtomic(amount: string | number) {
  const value = String(amount);
  if (!/^-?\d+(\.\d+)?$/.test(value)) throw new Error(`Invalid decimal amount: ${value}`);
  const negative = value.startsWith('-');
  const normalized = negative ? value.slice(1) : value;
  const [whole, fraction = ''] = normalized.split('.');
  const padded = `${fraction}${'0'.repeat(Number(SCALE))}`.slice(0, Number(SCALE));
  const atomic = BigInt(whole) * FACTOR + BigInt(padded || '0');
  return negative ? -atomic : atomic;
}

export function fromAtomic(value: bigint) {
  const negative = value < 0n;
  const abs = negative ? -value : value;
  const whole = abs / FACTOR;
  const fraction = (abs % FACTOR).toString().padStart(Number(SCALE), '0').replace(/0+$/, '');
  return `${negative ? '-' : ''}${whole.toString()}${fraction ? `.${fraction}` : ''}`;
}

export function add(a: string, b: string) {
  return fromAtomic(toAtomic(a) + toAtomic(b));
}

export function subtract(a: string, b: string) {
  return fromAtomic(toAtomic(a) - toAtomic(b));
}

export function multiplyBps(amount: string, bps: number) {
  return fromAtomic((toAtomic(amount) * BigInt(bps)) / 10_000n);
}

export function multiplyDecimal(a: string, b: string) {
  return fromAtomic((toAtomic(a) * toAtomic(b)) / FACTOR);
}

export function min(a: string, b: string) {
  return compare(a, b) <= 0 ? a : b;
}

export function compare(a: string, b: string) {
  const left = toAtomic(a);
  const right = toAtomic(b);
  return left === right ? 0 : left > right ? 1 : -1;
}

export function isPositive(amount: string) {
  return toAtomic(amount) > 0n;
}
