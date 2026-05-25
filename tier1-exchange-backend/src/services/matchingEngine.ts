import { randomUUID } from "node:crypto";
import type { DomainEvent, EventBus } from "../core/types.js";

export interface BookOrder {
  orderId: string;
  accountId: string;
  symbol: string;
  side: "buy" | "sell";
  orderType: "limit" | "market";
  price?: number;
  quantity: number;
  remainingQuantity: number;
  sequence: number;
  status: "open" | "partially_filled" | "filled" | "cancelled";
}

export interface Match {
  matchId: string;
  symbol: string;
  price: number;
  quantity: number;
  makerOrderId: string;
  takerOrderId: string;
  sequence: number;
}

export class DeterministicMatchingEngine {
  private sequence = 0;
  private readonly bids = new Map<string, BookOrder[]>();
  private readonly asks = new Map<string, BookOrder[]>();

  constructor(private readonly bus?: EventBus) {}

  async submit(
    order: Omit<BookOrder, "orderId" | "sequence" | "remainingQuantity" | "status"> & { orderId?: string },
  ): Promise<{ accepted: BookOrder; matches: Match[] }> {
    const accepted: BookOrder = {
      ...order,
      orderId: order.orderId ?? randomUUID(),
      sequence: ++this.sequence,
      remainingQuantity: order.quantity,
      status: "open",
    };
    if (accepted.orderType === "limit" && typeof accepted.price !== "number") {
      throw new Error("Limit orders require a price");
    }
    const opposite = accepted.side === "buy" ? this.asksFor(accepted.symbol) : this.bidsFor(accepted.symbol);
    const ownBook = accepted.side === "buy" ? this.bidsFor(accepted.symbol) : this.asksFor(accepted.symbol);
    const matches: Match[] = [];

    this.sortBook(opposite, accepted.side === "buy" ? "sell" : "buy");
    for (const resting of opposite) {
      if (accepted.remainingQuantity <= 0) break;
      const crosses = this.crosses(accepted, resting);
      if (!crosses) break;
      const quantity = Math.min(accepted.remainingQuantity, resting.remainingQuantity);
      resting.remainingQuantity -= quantity;
      accepted.remainingQuantity -= quantity;
      resting.status = resting.remainingQuantity === 0 ? "filled" : "partially_filled";
      accepted.status = accepted.remainingQuantity === 0 ? "filled" : "partially_filled";
      matches.push({
        matchId: randomUUID(),
        symbol: accepted.symbol,
        price: resting.price ?? 0,
        quantity,
        makerOrderId: resting.orderId,
        takerOrderId: accepted.orderId,
        sequence: ++this.sequence,
      });
    }

    removeFilled(opposite);
    if (accepted.remainingQuantity > 0 && accepted.orderType === "limit") {
      ownBook.push(accepted);
      this.sortBook(ownBook, accepted.side);
    }

    await this.publishAccepted(accepted);
    for (const match of matches) {
      await this.bus?.publish("matching.order.filled", accepted.orderId, {
        ...match,
        symbolPartition: partitionForSymbol(match.symbol),
      });
    }

    return { accepted, matches };
  }

  async cancel(symbol: string, orderId: string): Promise<{ cancelled: boolean; orderId: string; symbol: string }> {
    const order = [...this.bidsFor(symbol), ...this.asksFor(symbol)].find((candidate) => candidate.orderId === orderId);
    if (!order) return { cancelled: false, orderId, symbol };
    order.status = "cancelled";
    removeById(this.bidsFor(symbol), orderId);
    removeById(this.asksFor(symbol), orderId);
    await this.bus?.publish("matching.order.cancelled", orderId, {
      orderId,
      symbol,
      sequence: ++this.sequence,
      symbolPartition: partitionForSymbol(symbol),
    });
    return { cancelled: true, orderId, symbol };
  }

  snapshot(symbol: string): { symbolPartition: number; bids: BookOrder[]; asks: BookOrder[] } {
    return {
      symbolPartition: partitionForSymbol(symbol),
      bids: [...this.bidsFor(symbol)],
      asks: [...this.asksFor(symbol)],
    };
  }

  static reconstructFromEvents(symbol: string, events: DomainEvent[]): { accepted: DomainEvent[]; cancelled: DomainEvent[]; fills: DomainEvent[] } {
    const symbolEvents = events.filter((event) => String(event.payload.symbol) === symbol);
    return {
      accepted: symbolEvents.filter((event) => event.type === "matching.order.accepted"),
      cancelled: symbolEvents.filter((event) => event.type === "matching.order.cancelled"),
      fills: symbolEvents.filter((event) => event.type === "matching.order.filled"),
    };
  }

  private crosses(taker: BookOrder, maker: BookOrder): boolean {
    if (taker.orderType === "market") return true;
    if (typeof taker.price !== "number" || typeof maker.price !== "number") return false;
    return taker.side === "buy" ? taker.price >= maker.price : taker.price <= maker.price;
  }

  private async publishAccepted(order: BookOrder): Promise<void> {
    await this.bus?.publish("matching.order.accepted", order.orderId, {
      ...order,
      symbolPartition: partitionForSymbol(order.symbol),
      matchingMode: "deterministic-price-time-priority",
    });
  }

  private bidsFor(symbol: string): BookOrder[] {
    const book = this.bids.get(symbol) ?? [];
    this.bids.set(symbol, book);
    return book;
  }

  private asksFor(symbol: string): BookOrder[] {
    const book = this.asks.get(symbol) ?? [];
    this.asks.set(symbol, book);
    return book;
  }

  private sortBook(book: BookOrder[], side: "buy" | "sell"): void {
    book.sort((left, right) => {
      const leftPrice = left.price ?? (side === "buy" ? Number.NEGATIVE_INFINITY : Number.POSITIVE_INFINITY);
      const rightPrice = right.price ?? (side === "buy" ? Number.NEGATIVE_INFINITY : Number.POSITIVE_INFINITY);
      const priceCmp = side === "buy" ? rightPrice - leftPrice : leftPrice - rightPrice;
      return priceCmp || left.sequence - right.sequence;
    });
  }
}

function removeFilled(book: BookOrder[]): void {
  for (let index = book.length - 1; index >= 0; index -= 1) {
    if (book[index].remainingQuantity <= 0) book.splice(index, 1);
  }
}

function removeById(book: BookOrder[], orderId: string): void {
  for (let index = book.length - 1; index >= 0; index -= 1) {
    if (book[index].orderId === orderId) book.splice(index, 1);
  }
}

function partitionForSymbol(symbol: string, partitions = 32): number {
  let hash = 0;
  for (const char of symbol) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return hash % partitions;
}
