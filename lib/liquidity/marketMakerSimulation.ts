import { multiplyBps, multiplyDecimal, subtract, add } from '@/lib/exchange/money';

export function simulateMarketMaking(input: {
  midPrice: string;
  inventoryBase: string;
  inventoryQuote: string;
  spreadBps: number;
  orderSizeBase: string;
}) {
  const halfSpread = Math.floor(input.spreadBps / 2);
  const bid = subtract(input.midPrice, multiplyBps(input.midPrice, halfSpread));
  const ask = add(input.midPrice, multiplyBps(input.midPrice, halfSpread));
  const quoteRequired = multiplyDecimal(bid, input.orderSizeBase);
  return {
    bid,
    ask,
    bidSizeBase: input.orderSizeBase,
    askSizeBase: input.orderSizeBase,
    quoteRequired,
    canQuoteBid: Number(input.inventoryQuote) >= Number(quoteRequired),
    canQuoteAsk: Number(input.inventoryBase) >= Number(input.orderSizeBase),
  };
}
