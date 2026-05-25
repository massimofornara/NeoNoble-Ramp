import { createHash, createHmac } from "node:crypto";
import type { EventStore, LedgerStore } from "../core/store.js";

export class AuditService {
  constructor(
    private readonly events: EventStore,
    private readonly ledger: LedgerStore,
  ) {}

  transactionReport(transactionId: string): Record<string, unknown> {
    const events = this.events.byTransaction(transactionId);
    const ledgerEntries = this.ledger.byTransaction(transactionId);
    const eventDigest = createHash("sha256").update(JSON.stringify(events)).digest("hex");
    const ledgerDigest = createHash("sha256").update(JSON.stringify(ledgerEntries)).digest("hex");
    const report = {
      transactionId,
      eventCount: events.length,
      ledgerEntryCount: ledgerEntries.length,
      eventDigest,
      ledgerDigest,
      ledgerHashChain: this.ledger.verifyHashChain(),
      eventTypes: events.map((event) => event.type),
      txHashes: events
        .map((event) => event.payload.txHash)
        .filter((value): value is string => typeof value === "string"),
      settlementIds: events
        .map((event) => event.payload.settlementId)
        .filter((value): value is string => typeof value === "string"),
      valuations: events
        .map((event) => event.payload.valuation)
        .filter((value) => value && typeof value === "object"),
    };
    return {
      ...report,
      auditSignature: createHmac("sha256", process.env.AUDIT_SIGNING_KEY ?? "local-audit-signing-key")
        .update(JSON.stringify(report))
        .digest("hex"),
    };
  }
}
