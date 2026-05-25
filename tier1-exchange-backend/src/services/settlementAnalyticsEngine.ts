import type { EventStore, SettlementProofStore } from "../core/store.js";

export class SettlementAnalyticsEngine {
  constructor(
    private readonly events?: EventStore,
    private readonly proofs?: SettlementProofStore,
  ) {}

  report(): Record<string, unknown> {
    const events = this.events?.all() ?? [];
    const proofs = this.proofs?.all() ?? [];
    const confirmed = events.filter((event) => event.type === "settlement.confirmed").length;
    const initiated = events.filter((event) => event.type === "settlement.initiated").length;
    return {
      initiated,
      confirmed,
      failed: events.filter((event) => event.type === "settlement.failed").length,
      confirmationRate: initiated > 0 ? confirmed / initiated : 0,
      immutableProofs: proofs.length,
      latestProofHash: proofs.at(-1)?.currentHash ?? null,
    };
  }
}
