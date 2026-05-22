import { randomUUID } from "node:crypto";

export class RpcMonetizationService {
  constructor({ blockchainAdapters, developerPlatform, eventBus }) {
    this.blockchainAdapters = blockchainAdapters;
    this.developerPlatform = developerPlatform;
    this.eventBus = eventBus;
    this.relayLog = [];
    this.products = [
      { id: "premium-rpc", unit: "rpc_request", revenueUsdPerMillion: 18, margin: "high" },
      { id: "tx-accelerator", unit: "relay_submission", revenueUsdPerTx: 0.25, margin: "medium" },
      { id: "wallet-analytics", unit: "wallet_profile", revenueUsdPerThousand: 12, margin: "high" },
      { id: "webhook-streams", unit: "webhook_delivery", revenueUsdPerMillion: 8, margin: "high" }
    ];
  }

  async rpc({ apiKey, chain, method, params = [], ip }) {
    const auth = this.developerPlatform.authorize({ apiKey, route: "rpc.proxy", units: this.unitsFor(method), ip });
    if (!auth.allowed) throw new Error(auth.reason);
    const adapter = this.adapter(chain);
    const started = Date.now();
    try {
      const result = await adapter.call(method, params);
      this.developerPlatform.meter({
        apiKey: auth.apiKey,
        route: "rpc.proxy",
        chain,
        method,
        units: auth.units,
        latencyMs: Date.now() - started,
        revenueUsd: this.revenueForUnits(auth.units, auth.plan),
        ip
      });
      return { id: randomUUID(), chain, method, status: "ok", result };
    } catch (error) {
      this.developerPlatform.meter({ apiKey: auth.apiKey, route: "rpc.proxy", chain, method, units: auth.units, status: "error", latencyMs: Date.now() - started, ip });
      throw error;
    }
  }

  accelerationQuote({ chain, urgency = "standard", estimatedGas = 21000 }) {
    const multiplier = urgency === "urgent" ? 2.2 : urgency === "fast" ? 1.5 : 1;
    const serviceFeeUsd = round(0.15 * multiplier + Number(estimatedGas) / 1_000_000 * 0.05);
    return {
      chain,
      urgency,
      policy: "MEV-safe, user-consented relay only; no sandwiching, no private orderflow resale.",
      estimatedGas: Number(estimatedGas),
      serviceFeeUsd,
      route: urgency === "urgent" ? "private_relay_then_public_fallback" : "public_rpc_pool_with_retry"
    };
  }

  async relay({ apiKey, chain, rawTransaction, urgency = "standard", userConsent = false, ip }) {
    if (!userConsent) throw new Error("Explicit user consent required for tx relay");
    const auth = this.developerPlatform.authorize({ apiKey, route: "tx.relay", units: 50, ip });
    if (!auth.allowed) throw new Error(auth.reason);
    const adapter = this.adapter(chain);
    const quote = this.accelerationQuote({ chain, urgency });
    const started = Date.now();
    const txHash = await adapter.broadcast(rawTransaction);
    const relay = {
      id: randomUUID(),
      chain,
      txHash,
      urgency,
      quote,
      status: "submitted",
      latencyMs: Date.now() - started,
      createdAt: new Date().toISOString()
    };
    this.relayLog.push(relay);
    this.developerPlatform.meter({ apiKey: auth.apiKey, route: "tx.relay", chain, method: "broadcast", units: auth.units, revenueUsd: quote.serviceFeeUsd, latencyMs: relay.latencyMs, ip });
    this.eventBus.publish("TransactionRelayed", relay);
    return relay;
  }

  summary() {
    return {
      generatedAt: new Date().toISOString(),
      products: this.products,
      relays: this.relayLog,
      rpcStatus: Object.fromEntries(Object.entries(this.blockchainAdapters).map(([chain, adapter]) => [chain, adapter.status()])),
      monetization: [
        "Charge premium RPC by monthly plan plus overage.",
        "Charge tx acceleration as explicit service fee.",
        "Charge wallet analytics/API exports by unit.",
        "Charge webhook delivery and SLA packages for enterprise users."
      ]
    };
  }

  unitsFor(method) {
    if (/getLogs|trace|debug/i.test(method)) return 25;
    if (/eth_call|getProgramAccounts/i.test(method)) return 5;
    return 1;
  }

  revenueForUnits(units, plan) {
    return round(Number(units) / 1_000_000 * Number(plan.overageUsdPerMillion));
  }

  adapter(chain) {
    const adapter = this.blockchainAdapters[chain];
    if (!adapter) throw new Error(`Unsupported chain: ${chain}`);
    return adapter;
  }
}

function round(value) {
  return Math.round((Number(value) + Number.EPSILON) * 1e8) / 1e8;
}
