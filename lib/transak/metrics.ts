import { Counter, Gauge, Histogram, Registry, collectDefaultMetrics } from 'prom-client';

const registry = new Registry();
collectDefaultMetrics({ register: registry });

export const transakSessionCounter = new Counter({
  name: 'transak_widget_sessions_total',
  help: 'Total Transak widget sessions created',
  labelNames: ['environment', 'product'],
  registers: [registry],
});

export const transakWebhookCounter = new Counter({
  name: 'transak_webhook_events_total',
  help: 'Total Transak webhook events received',
  labelNames: ['event_name', 'result'],
  registers: [registry],
});

export const transakStatusHistogram = new Histogram({
  name: 'transak_status_request_duration_seconds',
  help: 'Duration for Transak status polling requests',
  buckets: [0.05, 0.1, 0.25, 0.5, 1, 2, 5],
  registers: [registry],
});

export const transakActiveSessionsGauge = new Gauge({
  name: 'transak_active_widget_sessions',
  help: 'Active Transak sessions tracked by NeoNoble',
  registers: [registry],
});

export const exchangeSwapCounter = new Counter({
  name: 'exchange_swaps_total',
  help: 'Total internal exchange swaps',
  labelNames: ['from_asset', 'to_asset', 'result'],
  registers: [registry],
});

export const exchangeSettlementLatency = new Histogram({
  name: 'exchange_settlement_latency_seconds',
  help: 'Internal exchange settlement latency',
  buckets: [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10],
  registers: [registry],
});

export const liquidityDepthGauge = new Gauge({
  name: 'exchange_liquidity_depth',
  help: 'Internal liquidity pool depth by asset pair',
  labelNames: ['base_asset', 'quote_asset', 'side'],
  registers: [registry],
});

export const riskEventCounter = new Counter({
  name: 'exchange_risk_events_total',
  help: 'Risk events emitted by exchange core',
  labelNames: ['risk_type', 'severity', 'blocked'],
  registers: [registry],
});

export async function metricsText() {
  return registry.metrics();
}
