import { createHash, randomBytes, randomUUID } from "node:crypto";

const now = () => Date.now();
const hourMs = 60 * 60 * 1000;

export class DeveloperPlatform {
  constructor({ eventBus, revenueEngine, config = {} }) {
    this.eventBus = eventBus;
    this.revenueEngine = revenueEngine;
    this.config = config;
    this.apiKeys = new Map();
    this.usage = [];
    this.subscriptions = [];
    this.customers = [];
    this.plans = [
      {
        id: "trial",
        name: "Developer Trial",
        monthlyUsd: 0,
        includedUnits: 100_000,
        overageUsdPerMillion: 0,
        hourlyLimit: 5_000,
        features: ["shared_rpc", "webhook_sandbox", "sdk_quickstart"]
      },
      {
        id: "starter",
        name: "Starter RPC",
        monthlyUsd: 99,
        includedUnits: 2_000_000,
        overageUsdPerMillion: 35,
        hourlyLimit: 60_000,
        features: ["shared_rpc", "basic_wallet_analytics", "community_support"]
      },
      {
        id: "pro",
        name: "Pro Infrastructure",
        monthlyUsd: 999,
        includedUnits: 50_000_000,
        overageUsdPerMillion: 18,
        hourlyLimit: 2_000_000,
        features: ["premium_rpc", "tx_relay", "webhooks", "analytics_api", "priority_support"]
      },
      {
        id: "enterprise",
        name: "Enterprise Chain Intelligence",
        monthlyUsd: 7500,
        includedUnits: 500_000_000,
        overageUsdPerMillion: 9,
        hourlyLimit: 25_000_000,
        features: ["dedicated_rpc_pool", "mev_safe_routing", "custom_sla", "data_exports", "private_slack"]
      }
    ];
    const bootstrapKey = config.bootstrapApiKey;
    if (bootstrapKey) {
      this.registerApiKey({ customerId: "platform", planId: "enterprise", label: "bootstrap", rawKey: bootstrapKey });
    }
  }

  registerApiKey({ customerId, planId = "starter", label = "default", rawKey } = {}) {
    if (!customerId) throw new Error("customerId required");
    const plan = this.plan(planId);
    const key = rawKey ?? `msv3_${randomBytes(24).toString("hex")}`;
    const record = {
      id: randomUUID(),
      keyHash: this.hash(key),
      customerId,
      planId: plan.id,
      label,
      status: "active",
      createdAt: new Date().toISOString()
    };
    this.apiKeys.set(record.keyHash, record);
    this.eventBus.publish("DeveloperApiKeyCreated", { ...record, keyPreview: `${key.slice(0, 10)}...` });
    return { ...record, apiKey: key };
  }

  onboard({ email, company, name, useCase = "premium_rpc", expectedMonthlyUnits = 0, planId = "trial", consent }) {
    if (!email || !String(email).includes("@")) throw new Error("Valid email required");
    if (!consent) throw new Error("Developer onboarding requires consent");
    const customer = {
      id: `dev-${randomUUID()}`,
      email: String(email).toLowerCase(),
      company,
      name,
      useCase,
      expectedMonthlyUnits: Number(expectedMonthlyUnits),
      status: planId === "trial" ? "trial" : "billing_required",
      createdAt: new Date().toISOString()
    };
    this.customers.push(customer);
    const subscription = this.subscribe({ customerId: customer.id, planId, status: planId === "trial" ? "trial" : "pending_payment" });
    const key = this.registerApiKey({ customerId: customer.id, planId, label: "self-service" });
    this.eventBus.publish("DeveloperOnboarded", { customer, subscriptionId: subscription.id, keyId: key.id });
    return {
      customer,
      subscription,
      apiKey: key.apiKey,
      quickstart: {
        rpc: "POST /rpc/proxy",
        webhooks: "POST /webhooks",
        invoices: "GET /developer/me",
        docs: "/developers"
      }
    };
  }

  subscribe({ customerId, planId, status = "active" }) {
    const plan = this.plan(planId);
    const subscription = {
      id: randomUUID(),
      customerId,
      planId: plan.id,
      status,
      monthlyUsd: plan.monthlyUsd,
      startedAt: new Date().toISOString()
    };
    this.subscriptions.push(subscription);
    this.eventBus.publish("DeveloperSubscriptionCreated", subscription);
    return subscription;
  }

  authorize({ apiKey, route, units = 1, ip = "unknown" }) {
    const record = this.apiKeyRecord(apiKey);
    if (!record || record.status !== "active") {
      return { allowed: false, status: 401, reason: "INVALID_API_KEY" };
    }
    const plan = this.plan(record.planId);
    const used = this.hourlyUsage(record.keyHash);
    if (used + units > plan.hourlyLimit) {
      return { allowed: false, status: 429, reason: "HOURLY_LIMIT_EXCEEDED", plan, used, requestedUnits: units };
    }
    return { allowed: true, apiKey: record, plan, route, units, ip };
  }

  meter({ apiKey, route, units = 1, chain, method, status = "ok", revenueUsd = 0, latencyMs = 0, ip = "unknown" }) {
    const record = typeof apiKey === "string" ? this.apiKeyRecord(apiKey) : apiKey;
    const row = {
      id: randomUUID(),
      customerId: record?.customerId ?? "anonymous",
      keyHash: record?.keyHash,
      planId: record?.planId ?? "none",
      route,
      chain,
      method,
      units: Number(units),
      status,
      revenueUsd: Number(revenueUsd),
      latencyMs: Number(latencyMs),
      ip,
      createdAt: new Date().toISOString(),
      ts: now()
    };
    this.usage.push(row);
    this.eventBus.publish("DeveloperUsageMetered", row);
    return row;
  }

  quoteInvoice({ customerId, period = "current" } = {}) {
    const rows = this.usage.filter((row) => !customerId || row.customerId === customerId);
    const byCustomer = new Map();
    for (const row of rows) {
      const aggregate = byCustomer.get(row.customerId) ?? { customerId: row.customerId, units: 0, meteredRevenueUsd: 0, plans: new Set() };
      aggregate.units += row.units;
      aggregate.meteredRevenueUsd += row.revenueUsd;
      aggregate.plans.add(row.planId);
      byCustomer.set(row.customerId, aggregate);
    }
    const invoices = [...byCustomer.values()].map((aggregate) => {
      const primaryPlan = this.plan([...aggregate.plans][0] === "none" ? "starter" : [...aggregate.plans][0]);
      const overageUnits = Math.max(0, aggregate.units - primaryPlan.includedUnits);
      const overageUsd = overageUnits / 1_000_000 * primaryPlan.overageUsdPerMillion;
      return {
        customerId: aggregate.customerId,
        period,
        planId: primaryPlan.id,
        baseUsd: primaryPlan.monthlyUsd,
        units: aggregate.units,
        includedUnits: primaryPlan.includedUnits,
        overageUnits,
        overageUsd: round(overageUsd),
        meteredRevenueUsd: round(aggregate.meteredRevenueUsd),
        invoiceUsd: round(primaryPlan.monthlyUsd + overageUsd + aggregate.meteredRevenueUsd)
      };
    });
    return { generatedAt: new Date().toISOString(), invoices };
  }

  summary() {
    const usageByRoute = countSum(this.usage, "route", "units");
    const usageByChain = countSum(this.usage, "chain", "units");
    const revenueUsd = round(this.usage.reduce((sum, row) => sum + row.revenueUsd, 0));
    return {
      generatedAt: new Date().toISOString(),
      plans: this.plans,
      customerCount: this.customers.length,
      apiKeyCount: this.apiKeys.size,
      subscriptionCount: this.subscriptions.length,
      usageCount: this.usage.length,
      usageUnits: this.usage.reduce((sum, row) => sum + row.units, 0),
      usageByRoute,
      usageByChain,
      meteredRevenueUsd: revenueUsd,
      invoicePreview: this.quoteInvoice()
    };
  }

  dashboard({ apiKey }) {
    const record = this.apiKeyRecord(apiKey);
    if (!record) throw new Error("INVALID_API_KEY");
    const customer = this.customers.find((row) => row.id === record.customerId) ?? { id: record.customerId, status: "active" };
    const plan = this.plan(record.planId);
    const usage = this.usage.filter((row) => row.keyHash === record.keyHash);
    const units = usage.reduce((sum, row) => sum + row.units, 0);
    const errors = usage.filter((row) => row.status === "error").length;
    return {
      generatedAt: new Date().toISOString(),
      customer,
      plan,
      usage: {
        units,
        includedUnits: plan.includedUnits,
        remainingIncludedUnits: Math.max(0, plan.includedUnits - units),
        hourlyUnits: this.hourlyUsage(record.keyHash),
        hourlyLimit: plan.hourlyLimit,
        errorRate: usage.length ? errors / usage.length : 0,
        byRoute: countSum(usage, "route", "units"),
        byChain: countSum(usage, "chain", "units")
      },
      invoice: this.quoteInvoice({ customerId: record.customerId }).invoices[0] ?? null
    };
  }

  hourlyUsage(keyHash) {
    const cutoff = now() - hourMs;
    return this.usage
      .filter((row) => row.keyHash === keyHash && row.ts >= cutoff)
      .reduce((sum, row) => sum + row.units, 0);
  }

  apiKeyRecord(apiKey) {
    if (!apiKey) return undefined;
    return this.apiKeys.get(this.hash(apiKey));
  }

  plan(planId) {
    const plan = this.plans.find((row) => row.id === planId);
    if (!plan) throw new Error(`Unknown API plan: ${planId}`);
    return plan;
  }

  hash(value) {
    return createHash("sha256").update(String(value)).digest("hex");
  }
}

function countSum(rows, keyField, valueField) {
  return rows.reduce((acc, row) => {
    const key = row[keyField] ?? "unknown";
    acc[key] = round((acc[key] ?? 0) + Number(row[valueField] ?? 0));
    return acc;
  }, {});
}

function round(value) {
  return Math.round((Number(value) + Number.EPSILON) * 1e8) / 1e8;
}
