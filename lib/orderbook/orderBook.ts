import { compare } from '@/lib/exchange/money';
import type { ClobOrderSide } from '@/types/tier1';

export type BookOrder = {
  id: string;
  userId: string;
  side: ClobOrderSide;
  price: string;
  remainingQuantity: string;
  sequence: number;
};

export class CentralLimitOrderBook {
  private bids: BookOrder[] = [];
  private asks: BookOrder[] = [];

  add(order: BookOrder) {
    if (order.side === 'BUY') {
      this.bids.push(order);
      this.bids.sort((a, b) => {
        const price = compare(b.price, a.price);
        return price !== 0 ? price : a.sequence - b.sequence;
      });
    } else {
      this.asks.push(order);
      this.asks.sort((a, b) => {
        const price = compare(a.price, b.price);
        return price !== 0 ? price : a.sequence - b.sequence;
      });
    }
  }

  bestBid() {
    return this.bids[0] || null;
  }

  bestAsk() {
    return this.asks[0] || null;
  }

  snapshot(depth = 25) {
    return {
      bids: this.bids.slice(0, depth),
      asks: this.asks.slice(0, depth),
    };
  }
}
