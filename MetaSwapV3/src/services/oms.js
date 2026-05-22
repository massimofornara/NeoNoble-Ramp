import { randomUUID } from "node:crypto";

export class OrderManagementService {
  constructor({ ledger, assetRegistry, pricingEngine, riskEngine, rfqEngine, matchingEngine, eventBus, circuitBreaker, surveillanceEngine, walletService, custodyService, revenueEngine }) {
    this.ledger = ledger;
    this.assetRegistry = assetRegistry;
    this.pricingEngine = pricingEngine;
    this.riskEngine = riskEngine;
    this.rfqEngine = rfqEngine;
    this.matchingEngine = matchingEngine;
    this.eventBus = eventBus;
    this.circuitBreaker = circuitBreaker;
    this.surveillanceEngine = surveillanceEngine;
    this.walletService = walletService;
    this.custodyService = custodyService;
    this.revenueEngine = revenueEngine;
    this.orders = [];
    this.trades = [];
  }

  async submitOrder({ userId, symbol, quoteAsset = "EUR", side, amount, type = "market", limitPrice, walletSessionId }) {
    symbol = symbol.toUpperCase();
    quoteAsset = quoteAsset.toUpperCase();
    const asset = this.assetRegistry.get(symbol);
    this.circuitBreaker?.assertOpen(`${symbol}-${quoteAsset}`);
    const estimate = limitPrice ?? this.pricingEngine.midPrice(symbol, quoteAsset);
    const risk = this.riskEngine.preTrade({ userId, symbol, quoteAsset, side, amount, estimatedPrice: estimate });
    if (risk.decision !== "ALLOW") {
      this.eventBus.publish("OrderRejected", { userId, symbol, quoteAsset, side, amount, reasons: risk.reasons });
      return { status: "rejected", risk };
    }

    const order = { id: randomUUID(), userId, symbol, quoteAsset, side, amount, type, status: "accepted", walletSessionId, createdAt: new Date().toISOString() };
    this.orders.push(order);
    this.eventBus.publish("OrderAccepted", order);

    if (asset.lifecycle === "liquid" || asset.lifecycle === "hybrid") {
      const execution = await this.executeOrderBook(order, limitPrice ?? estimate * (side === "buy" ? 1.02 : 0.98));
      if (execution.status === "filled") return execution;
    }

    return await this.executeRfq(order, risk.userRisk);
  }

  async executeOrderBook(order, limitPrice) {
    const market = `${order.symbol}-${order.quoteAsset}`;
    const result = this.matchingEngine.execute({ market, ownerId: order.userId, side: order.side, amount: order.amount, limitPrice });
    if (!result.fills.length) return { status: "unfilled", venue: "order-book", remaining: order.amount };
    let filled = 0;
    let quoteTotal = 0;
    for (const fill of result.fills) {
      await this.settleTrade({ order, price: fill.price, amount: fill.amount, provider: fill.makerOwnerId, venue: "order-book" });
      filled += fill.amount;
      quoteTotal += fill.price * fill.amount;
    }
    return { status: result.remaining <= 0 ? "filled" : "partial", venue: "order-book", orderId: order.id, filled, averagePrice: quoteTotal / filled, remaining: result.remaining };
  }

  async executeRfq(order, userRisk) {
    const quote = await this.rfqEngine.requestQuote({ userRisk, symbol: order.symbol, quoteAsset: order.quoteAsset, side: order.side, amount: order.amount });
    const trade = await this.settleTrade({ order, price: quote.price, amount: order.amount, provider: quote.provider, venue: "rfq" });
    return { status: "filled", venue: "rfq", orderId: order.id, quote, trade };
  }

  async settleTrade({ order, price, amount, provider, venue = "rfq" }) {
    const quoteAmount = Number((price * amount).toFixed(8));
    const commandId = order.id;
    const eventId = randomUUID();
    const asset = this.assetRegistry.get(order.symbol);
    const fee = this.revenueEngine?.tradeFee({ asset, venue, quoteAsset: order.quoteAsset, price, amount }) ?? { feeAmount: 0, asset: order.quoteAsset, revenueUsd: 0 };
    if (order.side === "buy") {
      const userQuote = this.ledger.ensureAccount("customer", order.userId, order.quoteAsset);
      const quoteAsset = this.assetRegistry.get(order.quoteAsset);
      const quoteOwner = quoteAsset.type === "fiat" ? "treasury" : "inventory";
      const platformQuote = this.ledger.ensureAccount("platform", quoteOwner, order.quoteAsset);
      const platformBase = this.ledger.ensureAccount("platform", "inventory", order.symbol);
      const userBase = this.ledger.ensureAccount("customer", order.userId, order.symbol);
      this.ledger.lock(userQuote, round(quoteAmount + fee.feeAmount));
      this.ledger.postTransfer({ from: userQuote, fromBucket: "locked", to: platformQuote, asset: order.quoteAsset, amount: quoteAmount, commandId, eventId, memo: "trade quote leg" });
      this.revenueEngine?.recordFee({ fee, from: userQuote, fromBucket: "locked", commandId, eventId, memo: "trade fee" });
      this.ledger.postTransfer({ from: platformBase, to: userBase, asset: order.symbol, amount, commandId, eventId, memo: "trade base leg" });
      this.pricingEngine.recordDemand(order.symbol, quoteAmount * this.pricingEngine.usdValue(order.quoteAsset));
    } else {
      const userBase = this.ledger.ensureAccount("customer", order.userId, order.symbol);
      const platformBase = this.ledger.ensureAccount("platform", "inventory", order.symbol);
      const quoteAsset = this.assetRegistry.get(order.quoteAsset);
      const quoteOwner = quoteAsset.type === "fiat" ? "treasury" : "inventory";
      const platformQuote = this.ledger.ensureAccount("platform", quoteOwner, order.quoteAsset);
      const userQuote = this.ledger.ensureAccount("customer", order.userId, order.quoteAsset);
      this.ledger.lock(userBase, amount);
      this.ledger.postTransfer({ from: userBase, fromBucket: "locked", to: platformBase, asset: order.symbol, amount, commandId, eventId, memo: "trade base leg" });
      this.ledger.postTransfer({ from: platformQuote, to: userQuote, asset: order.quoteAsset, amount: round(quoteAmount - fee.feeAmount), commandId, eventId, memo: "trade quote leg" });
      this.revenueEngine?.recordFee({ fee, from: platformQuote, commandId, eventId, memo: "trade fee" });
      this.pricingEngine.recordDemand(order.symbol, -quoteAmount * this.pricingEngine.usdValue(order.quoteAsset));
    }
    const trade = { id: randomUUID(), orderId: order.id, userId: order.userId, symbol: order.symbol, quoteAsset: order.quoteAsset, side: order.side, amount, price, quoteAmount, fee, netQuoteAmount: order.side === "sell" ? round(quoteAmount - fee.feeAmount) : quoteAmount, provider, createdAt: new Date().toISOString() };
    this.trades.push(trade);
    this.eventBus.publish("TradeExecuted", trade);
    this.surveillanceEngine?.recordTrade(trade);
    this.riskEngine.postTrade({ userId: order.userId, symbol: order.symbol, notionalUsd: quoteAmount * this.pricingEngine.usdValue(order.quoteAsset), tradeId: trade.id });
    if (order.walletSessionId) await this.deliverToWallet({ order, trade, amount, quoteAmount });
    return trade;
  }

  async deliverToWallet({ order, trade, amount, quoteAmount }) {
    const session = this.walletService.getSession(order.walletSessionId);
    if (session.userId !== order.userId) throw new Error("Wallet session does not belong to order user");
    const assetToDeliver = order.side === "buy" ? order.symbol : order.quoteAsset;
    const amountToDeliver = order.side === "buy" ? amount : quoteAmount;
    const asset = this.assetRegistry.get(assetToDeliver);
    if (asset.type === "fiat") return;
    const withdrawal = await this.custodyService.withdraw({
      userId: order.userId,
      asset: assetToDeliver,
      amount: amountToDeliver,
      chain: session.chain,
      address: session.address
    });
    this.eventBus.publish("TradeDeliveredToWallet", { tradeId: trade.id, walletSessionId: session.id, withdrawalId: withdrawal.id });
  }
}

function round(value) {
  return Math.round((Number(value) + Number.EPSILON) * 1e8) / 1e8;
}
