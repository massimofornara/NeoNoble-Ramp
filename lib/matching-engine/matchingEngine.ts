import { compare, min, multiplyDecimal, subtract } from '@/lib/exchange/money';
import { calculateFees } from '@/lib/matching-engine/feeEngine';
import type { ClobOrderRequest, MatchFill } from '@/types/tier1';

export type RestingOrder = {
  id: string;
  userId: string;
  side: 'BUY' | 'SELL';
  price: string;
  remainingQuantity: string;
  sequence: number;
};

export function canCross(taker: ClobOrderRequest, maker: RestingOrder) {
  if (taker.type === 'MARKET') return true;
  if (!taker.price) return false;
  return taker.side === 'BUY'
    ? compare(taker.price, maker.price) >= 0
    : compare(taker.price, maker.price) <= 0;
}

export function matchOrder(input: {
  takerOrderId: string;
  taker: ClobOrderRequest;
  resting: RestingOrder[];
  makerFeeBps: number;
  takerFeeBps: number;
}) {
  let remaining = input.taker.quantity;
  const fills: MatchFill[] = [];

  for (const maker of input.resting) {
    if (compare(remaining, '0') <= 0) break;
    if (!canCross(input.taker, maker)) break;
    const quantity = min(remaining, maker.remainingQuantity);
    const notional = multiplyDecimal(quantity, maker.price);
    const fees = calculateFees({
      notional,
      makerFeeBps: input.makerFeeBps,
      takerFeeBps: input.takerFeeBps,
    });

    fills.push({
      makerOrderId: maker.id,
      takerOrderId: input.takerOrderId,
      market: input.taker.market,
      price: maker.price,
      quantity,
      makerUserId: maker.userId,
      takerUserId: input.taker.userId,
      makerFee: fees.makerFee,
      takerFee: fees.takerFee,
    });

    remaining = subtract(remaining, quantity);
  }

  return { fills, remainingQuantity: remaining };
}
