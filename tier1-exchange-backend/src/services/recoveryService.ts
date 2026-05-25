import { createHash, randomUUID } from "node:crypto";
import { join } from "node:path";
import { atomicWriteJson, readJsonFile } from "../core/persistence.js";
import type { ExchangeStore } from "../core/store.js";

interface Snapshot {
  snapshotId: string;
  createdAt: string;
  eventOffset: number;
  eventDigest: string;
  ledgerDigest: string;
  settlementProofDigest: string;
  ledgerEntryCount: number;
  settlementProofCount: number;
  compactionWatermark: number;
}

export class RecoveryService {
  constructor(private readonly store: ExchangeStore) {}

  createLedgerSnapshot(): Snapshot {
    const events = this.store.events.all();
    const ledger = this.store.ledger.all();
    const proofs = this.store.settlementProofs.all();
    const snapshot: Snapshot = {
      snapshotId: randomUUID(),
      createdAt: new Date().toISOString(),
      eventOffset: Number(events.at(-1)?.offset ?? -1),
      eventDigest: digest(events),
      ledgerDigest: digest(ledger),
      settlementProofDigest: digest(proofs),
      ledgerEntryCount: ledger.length,
      settlementProofCount: proofs.length,
      compactionWatermark: Number(events.at(-1)?.offset ?? -1),
    };
    atomicWriteJson(join(this.store.paths.snapshotsDir, `${snapshot.snapshotId}.json`), snapshot);
    atomicWriteJson(join(this.store.paths.snapshotsDir, "latest.json"), snapshot);
    return snapshot;
  }

  latestSnapshot(): Snapshot | null {
    return readJsonFile<Snapshot | null>(join(this.store.paths.snapshotsDir, "latest.json"), null);
  }

  verifyRecovery(): Record<string, unknown> {
    const latest = this.latestSnapshot();
    if (!latest) {
      return { valid: false, reason: "snapshot_not_found" };
    }
    const events = this.store.events.all();
    const ledger = this.store.ledger.all();
    const proofs = this.store.settlementProofs.all();
    return {
      valid:
        latest.eventDigest === digest(events) &&
        latest.ledgerDigest === digest(ledger) &&
        latest.settlementProofDigest === digest(proofs) &&
        this.store.ledger.verifyHashChain().valid &&
        this.store.settlementProofs.verifyHashChain().valid,
      snapshotId: latest.snapshotId,
      eventOffset: latest.eventOffset,
      currentEventOffset: Number(events.at(-1)?.offset ?? -1),
      replayFromSnapshot: "deterministic-snapshot-plus-event-tail",
      ledgerHashChain: this.store.ledger.verifyHashChain(),
      settlementProofHashChain: this.store.settlementProofs.verifyHashChain(),
    };
  }

  exportBackup(): Record<string, unknown> {
    const backup = {
      backupId: randomUUID(),
      createdAt: new Date().toISOString(),
      cluster: this.store.events.clusterStatus(),
      events: this.store.events.all(),
      ledger: this.store.ledger.all(),
      settlementProofs: this.store.settlementProofs.all(),
      deadLetters: this.store.deadLetters.all(),
    };
    atomicWriteJson(join(this.store.paths.backupsDir, `${backup.backupId}.json`), backup);
    return {
      backupId: backup.backupId,
      createdAt: backup.createdAt,
      eventCount: backup.events.length,
      ledgerEntryCount: backup.ledger.length,
      settlementProofCount: backup.settlementProofs.length,
      path: join(this.store.paths.backupsDir, `${backup.backupId}.json`),
    };
  }

  compactionPlan(): Record<string, unknown> {
    const snapshot = this.latestSnapshot();
    return {
      strategy: "snapshot-indexed-log-compaction",
      destructiveCompactionEnabled: false,
      reason: "event log remains legal source of truth; compaction is expressed as a verified snapshot watermark",
      snapshotWatermark: snapshot?.compactionWatermark ?? null,
      retainedEventLog: this.store.paths.eventsFile,
    };
  }
}

function digest(value: unknown): string {
  return createHash("sha256").update(JSON.stringify(value)).digest("hex");
}
