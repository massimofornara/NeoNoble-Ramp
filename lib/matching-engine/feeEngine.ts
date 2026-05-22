import { multiplyBps } from '@/lib/exchange/money';

export function calculateFees(input: {
  notional: string;
  makerFeeBps: number;
  takerFeeBps: number;
}) {
  return {
    makerFee: multiplyBps(input.notional, input.makerFeeBps),
    takerFee: multiplyBps(input.notional, input.takerFeeBps),
  };
}
