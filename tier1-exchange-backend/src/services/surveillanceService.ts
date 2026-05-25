import type { EventStore } from "../core/store.js";

export class SurveillanceService {
  constructor(private readonly events?: EventStore) {}

  abnormalExecutionScore(accountId: string): number {
    const recent = this.events
      ?.all()
      .filter((event) => event.payload.accountId === accountId && Date.now() - Date.parse(event.timestamp) < 60 * 60 * 1000).length ?? 0;
    return Math.min(1, recent / Number(process.env.SURVEILLANCE_EVENTS_PER_HOUR_LIMIT ?? 100));
  }
}
