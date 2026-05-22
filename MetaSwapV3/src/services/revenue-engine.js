const round = (value) => Math.round((Number(value) + Number.EPSILON) * 1e8) / 1e8;

export class RevenueEngine {
  constructor({ ledger, pricingEngine, eventBus }) {
    this.ledger = ledger;
    this.pricingEngine = pricingEngine;
    this.eventBus = eventBus;
    this.targetMonthlyUsd = 10_000_000;
    this.rules = {
      liquidTradingBps: 18,
      rfqTradingBps: 45,
      customTokenTradingBps: 65,
      fiatPayoutBps: 70,
      minFiatPayoutFee: 1.5,
      tokenLaunchFeeUsd: 2500,
      custodyWithdrawalBps: 25
    };
  }

  tradeFee({ asset, venue, quoteAsset, price, amount }) {
    const notional = round(price * amount);
    const bps = asset?.type === "token"
      ? this.rules.customTokenTradingBps
      : venue === "rfq"
        ? this.rules.rfqTradingBps
        : this.rules.liquidTradingBps;
    const feeAmount = round(notional * bps / 10_000);
    return this.feeQuote({ source: "trading", asset: quoteAsset, feeAmount, bps, notional });
  }

  fiatPayoutFee({ asset, amount }) {
    const bpsFee = round(amount * this.rules.fiatPayoutBps / 10_000);
    const feeAmount = round(Math.max(bpsFee, asset === "EUR" || asset === "USD" ? this.rules.minFiatPayoutFee : bpsFee));
    return this.feeQuote({ source: "fiat_payout", asset, feeAmount, bps: this.rules.fiatPayoutBps, notional: amount });
  }

  custodyWithdrawalFee({ asset, amount }) {
    const feeAmount = round(amount * this.rules.custodyWithdrawalBps / 10_000);
    return this.feeQuote({ source: "custody_withdrawal", asset, feeAmount, bps: this.rules.custodyWithdrawalBps, notional: amount });
  }

  feeQuote({ source, asset, feeAmount, bps, notional }) {
    const usd = round(feeAmount * this.pricingEngine.usdValue(asset));
    return {
      source,
      asset,
      feeAmount,
      bps,
      notional,
      revenueUsd: usd
    };
  }

  feeAccount(asset) {
    return this.ledger.ensureAccount("platform", "fees", asset);
  }

  recordFee({ fee, from, fromBucket = "available", memo, commandId, eventId }) {
    if (!fee?.feeAmount) return undefined;
    const entry = this.ledger.postTransfer({
      from,
      fromBucket,
      to: this.feeAccount(fee.asset),
      asset: fee.asset,
      amount: fee.feeAmount,
      commandId,
      eventId,
      memo: memo ?? `${fee.source} fee`
    });
    this.eventBus.publish("RevenueFeeCaptured", { ...fee, entryId: entry.id });
    return entry;
  }

  summary({ targetMonthlyUsd = this.targetMonthlyUsd } = {}) {
    const fees = [];
    for (const [accountId, account] of this.ledger.accounts.entries()) {
      if (account.ownerType !== "platform" || account.ownerId !== "fees") continue;
      const balance = this.ledger.balance(accountId);
      const available = round(balance.available);
      const valueUsd = round(available * this.pricingEngine.usdValue(account.asset));
      fees.push({ accountId, asset: account.asset, available, valueUsd });
    }
    const capturedRevenueUsd = round(fees.reduce((sum, row) => sum + row.valueUsd, 0));
    const targetGapUsd = round(Math.max(0, targetMonthlyUsd - capturedRevenueUsd));
    const requiredMonthlyVolume = this.requiredVolumeForTarget(targetMonthlyUsd);
    return {
      generatedAt: new Date().toISOString(),
      targetMonthlyUsd,
      capturedRevenueUsd,
      targetGapUsd,
      fees,
      requiredMonthlyVolume,
      monetizationLevers: [
        "custom token launch fees",
        "RFQ/custom-token trading spread and fee",
        "fiat payout fee",
        "custody withdrawal fee",
        "issuer premium market-making package",
        "enterprise API/FIX connectivity"
      ]
    };
  }

  scalePlan({
    primaryTargetMonthlyUsd = Number(process.env.REVENUE_TARGET_MONTHLY_USD ?? 1_000_000),
    nextTargetMonthlyUsd = Number(process.env.REVENUE_NEXT_TARGET_MONTHLY_USD ?? 10_000_000)
  } = {}) {
    const current = this.summary({ targetMonthlyUsd: primaryTargetMonthlyUsd });
    const activeTargetMonthlyUsd = current.capturedRevenueUsd >= primaryTargetMonthlyUsd
      ? nextTargetMonthlyUsd
      : primaryTargetMonthlyUsd;
    const active = activeTargetMonthlyUsd === primaryTargetMonthlyUsd
      ? current
      : this.summary({ targetMonthlyUsd: activeTargetMonthlyUsd });
    return {
      generatedAt: new Date().toISOString(),
      activeTargetMonthlyUsd,
      primaryTargetMonthlyUsd,
      nextTargetMonthlyUsd,
      escalated: activeTargetMonthlyUsd === nextTargetMonthlyUsd,
      capturedRevenueUsd: active.capturedRevenueUsd,
      targetGapUsd: active.targetGapUsd,
      requiredMonthlyVolume: active.requiredMonthlyVolume,
      distributionAccountCount: active.fees.length
    };
  }

  requiredVolumeForTarget(targetMonthlyUsd = this.targetMonthlyUsd) {
    const blendedTakeRateBps = 55;
    const monthlyVolumeUsd = round(targetMonthlyUsd / (blendedTakeRateBps / 10_000));
    return {
      blendedTakeRateBps,
      monthlyVolumeUsd,
      dailyVolumeUsd: round(monthlyVolumeUsd / 30),
      notes: `At ${blendedTakeRateBps} bps blended net revenue, $${round(targetMonthlyUsd).toLocaleString("en-US")} monthly revenue requires about $${round(monthlyVolumeUsd).toLocaleString("en-US")} monthly volume.`
    };
  }
}
