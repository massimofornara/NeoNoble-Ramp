import type { EventStore } from "../core/store.js";

export class LiquidityTelemetry {
  constructor(private readonly events?: EventStore) {}

  snapshot(): Record<string, unknown> {
    const events = this.events?.all() ?? [];
    return {
      intents: events.filter((event) => event.type === "execution.intent_created").length,
      scheduled: events.filter((event) => event.type === "execution.scheduled").length,
      completed: events.filter((event) => event.type === "execution.completed").length,
      confirmed: events.filter((event) => event.type === "settlement.confirmed").length,
      failed: events.filter((event) => event.type === "execution.failed" || event.type === "settlement.failed").length,
      capturedAt: new Date().toISOString(),
    };
  }
}
