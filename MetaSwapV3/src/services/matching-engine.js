export class MatchingEngine {
  constructor(eventBus) {
    this.eventBus = eventBus;
    this.books = new Map();
    this.sequence = 0;
  }

  book(market) {
    if (!this.books.has(market)) this.books.set(market, { bids: [], asks: [] });
    return this.books.get(market);
  }

  addRestingOrder({ market, ownerId, side, price, amount }) {
    const order = { id: `book-${++this.sequence}`, market, ownerId, side, price, remaining: amount, createdSeq: this.sequence };
    const book = this.book(market);
    const sideBook = side === "buy" ? book.bids : book.asks;
    sideBook.push(order);
    this.sortBook(book);
    return order;
  }

  execute({ market, ownerId, side, amount, limitPrice }) {
    const book = this.book(market);
    const opposite = side === "buy" ? book.asks : book.bids;
    const fills = [];
    let remaining = amount;
    for (const resting of opposite) {
      if (remaining <= 0) break;
      const crosses = side === "buy" ? resting.price <= limitPrice : resting.price >= limitPrice;
      if (!crosses) continue;
      const fillAmount = Math.min(remaining, resting.remaining);
      resting.remaining -= fillAmount;
      remaining -= fillAmount;
      fills.push({ makerOrderId: resting.id, makerOwnerId: resting.ownerId, takerOwnerId: ownerId, price: resting.price, amount: fillAmount });
    }
    book.asks = book.asks.filter((o) => o.remaining > 0);
    book.bids = book.bids.filter((o) => o.remaining > 0);
    this.sortBook(book);
    this.eventBus.publish("OrderBookExecuted", { market, ownerId, side, amount, limitPrice, fills, remaining });
    return { fills, remaining };
  }

  sortBook(book) {
    book.bids.sort((a, b) => b.price - a.price || a.createdSeq - b.createdSeq);
    book.asks.sort((a, b) => a.price - b.price || a.createdSeq - b.createdSeq);
  }

  depth(market) {
    const book = this.book(market);
    return { bids: book.bids.slice(0, 10), asks: book.asks.slice(0, 10) };
  }
}
