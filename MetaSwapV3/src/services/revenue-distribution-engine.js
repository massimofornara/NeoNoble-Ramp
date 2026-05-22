import { randomUUID } from "node:crypto";

const FIAT = new Set(["EUR", "USD"]);
const round = (value) => Math.round((Number(value) + Number.EPSILON) * 1e8) / 1e8;

export class RevenueDistributionEngine {
  constructor({ ledger, pricingEngine, railOrchestrator, eventBus, config = {} }) {
    this.ledger = ledger;
    this.pricingEngine = pricingEngine;
    this.railOrchestrator = railOrchestrator;
    this.eventBus = eventBus;
    this.config = config;
    this.distributions = [];
  }

  plan() {
    const feeAccounts = this.feeAccounts();
    const routes = [];
    const blockers = [];
    for (const account of feeAccounts) {
      const valueUsd = round(account.available * this.pricingEngine.usdValue(account.asset));
      if (account.available <= 0) continue;
      if (valueUsd < this.config.minSweepUsd) {
        blockers.push({ code: "BELOW_MIN_SWEEP", asset: account.asset, available: account.available, valueUsd, minSweepUsd: this.config.minSweepUsd });
        continue;
      }
      if (FIAT.has(account.asset)) routes.push(...this.planFiat(account));
      else routes.push(this.planCrypto(account));
    }
    for (const route of routes) {
      if (route.status !== "ready") blockers.push(...route.blockers);
    }
    return {
      generatedAt: new Date().toISOString(),
      autoSweepEnabled: Boolean(this.config.autoSweepEnabled),
      feeAccounts,
      routes,
      blockers,
      status: routes.length && !blockers.length ? "ready" : "blocked_or_empty",
      distributions: this.distributions
    };
  }

  async sweep({ asset, maxAmount } = {}) {
    const plan = this.plan();
    const selected = plan.routes.filter((route) => (!asset || route.asset === asset) && route.status === "ready");
    const executed = [];
    const blocked = plan.blockers.slice();
    for (const route of selected) {
      if (route.type === "fiat") executed.push(await this.executeFiatRoute(route, maxAmount));
      else blocked.push({ code: "CRYPTO_SWEEP_REQUIRES_LIVE_CUSTODY_BROADCASTER", asset: route.asset, destination: route.destination });
    }
    const result = {
      status: executed.length && !blocked.length ? "submitted" : executed.length ? "partial" : "blocked",
      executed,
      blocked,
      createdAt: new Date().toISOString()
    };
    this.eventBus.publish("RevenueDistributionSweepEvaluated", result);
    return result;
  }

  feeAccounts() {
    const rows = [];
    for (const [accountId, account] of this.ledger.accounts.entries()) {
      if (account.ownerType !== "platform" || account.ownerId !== "fees") continue;
      const balance = this.ledger.balance(accountId);
      rows.push({
        accountId,
        asset: account.asset,
        available: round(balance.available),
        valueUsd: round(balance.available * this.pricingEngine.usdValue(account.asset))
      });
    }
    return rows;
  }

  planFiat(account) {
    const destinations = this.normalizedFiatDestinations(account.asset);
    if (!destinations.length) {
      return [{
        type: "fiat",
        asset: account.asset,
        amount: account.available,
        status: "blocked",
        blockers: [{ code: "NO_FIAT_REVENUE_DESTINATIONS", asset: account.asset }]
      }];
    }
    return destinations.map((destination) => {
      const amount = round(account.available * destination.shareBps / 10_000);
      const blockers = [];
      if (!destination.name) blockers.push({ code: "MISSING_BENEFICIARY_NAME", iban: destination.iban });
      if (!destination.iban) blockers.push({ code: "MISSING_IBAN", id: destination.id });
      return {
        type: "fiat",
        asset: account.asset,
        amount,
        status: blockers.length ? "blocked" : "ready",
        destination,
        blockers
      };
    }).filter((route) => route.amount > 0);
  }

  planCrypto(account) {
    const blockers = [];
    if (!this.config.cryptoWallet) blockers.push({ code: "NO_CRYPTO_REVENUE_WALLET", asset: account.asset });
    return {
      type: "crypto",
      asset: account.asset,
      amount: account.available,
      status: blockers.length ? "blocked" : "ready",
      destination: {
        chain: this.config.cryptoChain ?? "ethereum",
        address: this.config.cryptoWallet
      },
      blockers
    };
  }

  normalizedFiatDestinations(asset) {
    const destinations = (this.config.fiatDestinations ?? []).filter((destination) => destination.asset === asset);
    if (!destinations.length) return [];
    const explicit = destinations.reduce((sum, destination) => sum + Number(destination.shareBps || 0), 0);
    const missing = destinations.filter((destination) => !destination.shareBps).length;
    const fallbackShare = missing ? Math.floor((10_000 - explicit) / missing) : 0;
    return destinations.map((destination) => ({
      ...destination,
      shareBps: Number(destination.shareBps || fallbackShare)
    }));
  }

  async executeFiatRoute(route, maxAmount) {
    const amount = round(Math.min(route.amount, maxAmount ? Number(maxAmount) : route.amount));
    if (amount <= 0) throw new Error("Sweep amount must be positive");
    const source = this.ledger.ensureAccount("platform", "fees", route.asset);
    if (this.ledger.balance(source).available < amount) throw new Error(`Insufficient platform fee balance for ${route.asset}`);
    const external = this.ledger.ensureAccount("external", `revenue:${route.destination.iban}`, route.asset);
    const reference = `rev-${Date.now()}-${randomUUID().slice(0, 8)}`;
    const instruction = {
      reference,
      userId: "platform-revenue",
      asset: route.asset,
      amount,
      rail: route.destination.rail ?? "SEPA",
      destination: {
        iban: route.destination.iban,
        name: route.destination.name
      }
    };
    const externalSubmission = await this.railOrchestrator.submitPayout(instruction);
    const entry = this.ledger.postTransfer({ from: source, to: external, asset: route.asset, amount, memo: "revenue distribution fiat sweep" });
    const distribution = {
      id: randomUUID(),
      reference,
      type: "fiat",
      asset: route.asset,
      amount,
      destination: route.destination,
      status: "submitted",
      externalSubmission,
      entryId: entry.id,
      createdAt: new Date().toISOString()
    };
    this.distributions.push(distribution);
    this.eventBus.publish("RevenueDistributionSubmitted", distribution);
    return distribution;
  }
}
