export class MetricsService {
  constructor({ eventBus, ledger, assetRegistry, developerPlatform, revenueEngine, webhookService, enterpriseSalesEngine }) {
    this.eventBus = eventBus;
    this.ledger = ledger;
    this.assetRegistry = assetRegistry;
    this.developerPlatform = developerPlatform;
    this.revenueEngine = revenueEngine;
    this.webhookService = webhookService;
    this.enterpriseSalesEngine = enterpriseSalesEngine;
  }

  prometheus() {
    const counts = new Map();
    for (const event of this.eventBus.events) counts.set(event.type, (counts.get(event.type) ?? 0) + 1);
    const lines = [
      "# HELP metaswap_events_total Total events by type",
      "# TYPE metaswap_events_total counter"
    ];
    for (const [type, count] of counts.entries()) {
      lines.push(`metaswap_events_total{type="${type}"} ${count}`);
    }
    lines.push("# HELP metaswap_ledger_journal_entries Ledger journal entries");
    lines.push("# TYPE metaswap_ledger_journal_entries gauge");
    lines.push(`metaswap_ledger_journal_entries ${this.ledger.journal.length}`);
    lines.push("# HELP metaswap_assets_registered Registered assets");
    lines.push("# TYPE metaswap_assets_registered gauge");
    lines.push(`metaswap_assets_registered ${this.assetRegistry.list().length}`);
    const developer = this.developerPlatform?.summary();
    if (developer) {
      lines.push("# HELP metaswap_developer_usage_units_total Developer platform usage units");
      lines.push("# TYPE metaswap_developer_usage_units_total counter");
      lines.push(`metaswap_developer_usage_units_total ${developer.usageUnits}`);
      lines.push("# HELP metaswap_developer_api_keys Developer API keys");
      lines.push("# TYPE metaswap_developer_api_keys gauge");
      lines.push(`metaswap_developer_api_keys ${developer.apiKeyCount}`);
      lines.push("# HELP metaswap_developer_metered_revenue_usd Metered infrastructure revenue USD");
      lines.push("# TYPE metaswap_developer_metered_revenue_usd gauge");
      lines.push(`metaswap_developer_metered_revenue_usd ${developer.meteredRevenueUsd}`);
    }
    const revenue = this.revenueEngine?.summary({ targetMonthlyUsd: Number(process.env.REVENUE_TARGET_MONTHLY_USD ?? 1_000_000) });
    if (revenue) {
      lines.push("# HELP metaswap_revenue_captured_usd Captured platform revenue USD");
      lines.push("# TYPE metaswap_revenue_captured_usd gauge");
      lines.push(`metaswap_revenue_captured_usd ${revenue.capturedRevenueUsd}`);
      lines.push("# HELP metaswap_revenue_target_gap_usd Revenue target gap USD");
      lines.push("# TYPE metaswap_revenue_target_gap_usd gauge");
      lines.push(`metaswap_revenue_target_gap_usd ${revenue.targetGapUsd}`);
    }
    const webhooks = this.webhookService?.summary();
    if (webhooks) {
      lines.push("# HELP metaswap_webhook_deliveries_queued Queued webhook deliveries");
      lines.push("# TYPE metaswap_webhook_deliveries_queued gauge");
      lines.push(`metaswap_webhook_deliveries_queued ${webhooks.queued}`);
    }
    const enterprise = this.enterpriseSalesEngine?.summary();
    if (enterprise) {
      lines.push("# HELP metaswap_enterprise_leads Enterprise B2B leads");
      lines.push("# TYPE metaswap_enterprise_leads gauge");
      lines.push(`metaswap_enterprise_leads ${enterprise.leadCount}`);
      lines.push("# HELP metaswap_enterprise_proposals Enterprise B2B proposals");
      lines.push("# TYPE metaswap_enterprise_proposals gauge");
      lines.push(`metaswap_enterprise_proposals ${enterprise.proposalCount}`);
      lines.push("# HELP metaswap_enterprise_verified_mrr_usd Reconciled enterprise MRR USD");
      lines.push("# TYPE metaswap_enterprise_verified_mrr_usd gauge");
      lines.push(`metaswap_enterprise_verified_mrr_usd ${enterprise.verifiedMrrUsd}`);
    }
    return `${lines.join("\n")}\n`;
  }
}
