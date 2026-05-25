import { randomUUID } from "node:crypto";

type Labels = Record<string, string | number | boolean | undefined>;

export class MetricsRegistry {
  private readonly counters = new Map<string, number>();
  private readonly histograms = new Map<string, number[]>();

  inc(name: string, labels: Labels = {}, value = 1): void {
    const key = metricKey(name, labels);
    this.counters.set(key, (this.counters.get(key) ?? 0) + value);
  }

  observe(name: string, value: number, labels: Labels = {}): void {
    const key = metricKey(name, labels);
    const values = this.histograms.get(key) ?? [];
    values.push(value);
    this.histograms.set(key, values);
  }

  toPrometheus(): string {
    const lines: string[] = [
      "# HELP exchange_event_throughput_total Events published by type.",
      "# TYPE exchange_event_throughput_total counter",
      "# HELP exchange_dlq_total Dead-lettered consumer events.",
      "# TYPE exchange_dlq_total counter",
      "# HELP exchange_execution_latency_ms Execution latency.",
      "# TYPE exchange_execution_latency_ms summary",
      "# HELP exchange_settlement_latency_ms Settlement latency.",
      "# TYPE exchange_settlement_latency_ms summary",
      "# HELP exchange_replay_duration_ms Replay duration.",
      "# TYPE exchange_replay_duration_ms summary",
      "# HELP exchange_reconciliation_integrity_failures_total Reconciliation integrity failures.",
      "# TYPE exchange_reconciliation_integrity_failures_total counter",
      "# HELP exchange_execution_failures_total Execution failures by classified reason.",
      "# TYPE exchange_execution_failures_total counter",
      "# HELP exchange_settlement_failures_total Settlement failures by classified reason.",
      "# TYPE exchange_settlement_failures_total counter",
    ];
    for (const [key, value] of this.counters.entries()) {
      lines.push(`${key} ${value}`);
    }
    for (const [key, values] of this.histograms.entries()) {
      const count = values.length;
      const sum = values.reduce((left, right) => left + right, 0);
      lines.push(`${key}_count ${count}`);
      lines.push(`${key}_sum ${sum}`);
      if (count > 0) lines.push(`${key}_avg ${sum / count}`);
    }
    return `${lines.join("\n")}\n`;
  }
}

export const metrics = new MetricsRegistry();

export function logJson(component: string, message: string, fields: Record<string, unknown> = {}): void {
  if (process.env.SUPPRESS_EVENT_STREAM_LOGS === "1" && component === "event-stream") return;
  console.log(
    JSON.stringify({
      level: fields.level ?? "info",
      component,
      message,
      timestamp: new Date().toISOString(),
      ...fields,
    }),
  );
}

export function startSpan(name: string, correlationId: string = randomUUID()): { traceId: string; spanId: string; end: (fields?: Record<string, unknown>) => void } {
  const traceId = correlationId.replace(/-/g, "").padEnd(32, "0").slice(0, 32);
  const spanId = randomUUID().replace(/-/g, "").slice(0, 16);
  const start = Date.now();
  logJson("otel-tracer", "span_start", { traceId, spanId, spanName: name });
  return {
    traceId,
    spanId,
    end(fields = {}) {
      logJson("otel-tracer", "span_end", { traceId, spanId, spanName: name, durationMs: Date.now() - start, ...fields });
    },
  };
}

function metricKey(name: string, labels: Labels): string {
  const entries = Object.entries(labels).filter(([, value]) => value !== undefined);
  if (entries.length === 0) return name;
  return `${name}{${entries.map(([key, value]) => `${key}="${String(value)}"`).join(",")}}`;
}
