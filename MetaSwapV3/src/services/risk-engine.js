export class RiskEngine {
  constructor({ complianceHub, ledger, assetRegistry, pricingEngine, eventBus }) {
    this.complianceHub = complianceHub;
    this.ledger = ledger;
    this.assetRegistry = assetRegistry;
    this.pricingEngine = pricingEngine;
    this.eventBus = eventBus;
    this.clusterExposure = new Map();
    this.assetExposureLimitsUsd = new Map();
    this.assetExposureLimitsUsd.set("default", 1_000_000);
  }

  preTrade({ userId, symbol, quoteAsset, side, amount, estimatedPrice }) {
    const user = this.complianceHub.getUser(userId);
    const asset = this.assetRegistry.get(symbol);
    const quote = this.assetRegistry.get(quoteAsset);
    const reasons = [];
    const compliance = this.complianceHub.screenUser(user, asset);
    reasons.push(...compliance.reasons);

    const price = estimatedPrice ?? this.pricingEngine.midPrice(symbol, quoteAsset);
    const notionalQuote = amount * price;
    const notionalUsd = notionalQuote * this.pricingEngine.usdValue(quote.symbol);
    const amlScore = this.complianceHub.scoreAml({ user, amountUsd: notionalUsd });
    if (amlScore >= 0.75) reasons.push("AML_SCORE_TOO_HIGH");
    if (amount <= 0) reasons.push("INVALID_AMOUNT");
    if (notionalUsd > this.limitFor(symbol)) reasons.push("ASSET_EXPOSURE_LIMIT");
    if (asset.lifecycle === "restricted") reasons.push("ASSET_RESTRICTED");

    const fundingAsset = side === "buy" ? quoteAsset : symbol;
    const required = side === "buy" ? notionalQuote : amount;
    const available = this.ledger.available("customer", userId, fundingAsset);
    if (available + 0.00000001 < required) reasons.push("INSUFFICIENT_BALANCE");

    const decision = reasons.length === 0 ? "ALLOW" : "BLOCK";
    const result = { decision, reasons, notionalUsd, amlScore, userRisk: user.fraudScore };
    this.eventBus.publish("PreTradeRiskEvaluated", { userId, symbol, side, amount, result });
    return result;
  }

  postTrade({ userId, symbol, notionalUsd, tradeId }) {
    const user = this.complianceHub.getUser(userId);
    const amlScore = this.complianceHub.scoreAml({ user, amountUsd: notionalUsd });
    const result = { tradeId, amlScore, action: amlScore >= 0.8 ? "HOLD_AND_REVIEW" : "CLEAR" };
    if (result.action !== "CLEAR") this.complianceHub.openCase("AML", userId, "High post-trade AML score", "high");
    this.eventBus.publish("PostTradeRiskEvaluated", { userId, symbol, result });
    return result;
  }

  limitFor(symbol) {
    return this.assetExposureLimitsUsd.get(symbol) ?? this.assetExposureLimitsUsd.get("default");
  }
}
