import { createHash, randomUUID } from "node:crypto";
import { join } from "node:path";
import type { DeadLetterRecord, DomainEvent, FireblocksTransactionRecord, LedgerEntry, SettlementProof } from "./types.js";
import { appendJsonLine, AsyncMutex, atomicWriteJson, ensureDir, readJsonFile, readJsonLines } from "./persistence.js";
import { PostgresPersistence } from "./postgresPersistence.js";

const ZERO_HASH = "0".repeat(64);

export interface StorePaths {
  dataDir: string;
  eventsFile: string;
  replicaEventFiles: string[];
  clusterStateFile: string;
  ledgerFile: string;
  settlementProofsFile: string;
  fireblocksTransactionsFile: string;
  deadLetterFile: string;
  idempotencyFile: string;
  consumerOffsetsFile: string;
  processedEventsFile: string;
  webhookNoncesFile: string;
  snapshotsDir: string;
  backupsDir: string;
}

export interface ClusterNodeState {
  nodeId: string;
  path: string;
  role: "leader" | "follower";
  status: "active" | "offline" | "recovering";
  lastHeartbeat: string;
  partitions: number[];
}

export interface ClusterState {
  epoch: number;
  leaderId: string;
  partitionCount: number;
  nodes: ClusterNodeState[];
}

export function defaultStorePaths(dataDir = process.env.TIER1_DATA_DIR || "./data"): StorePaths {
  return {
    dataDir,
    eventsFile: join(dataDir, "event-stream.jsonl"),
    replicaEventFiles: [
      join(dataDir, "replicas", "node-1", "event-stream.jsonl"),
      join(dataDir, "replicas", "node-2", "event-stream.jsonl"),
      join(dataDir, "replicas", "node-3", "event-stream.jsonl"),
    ],
    clusterStateFile: join(dataDir, "cluster-state.json"),
    ledgerFile: join(dataDir, "ledger.jsonl"),
    settlementProofsFile: join(dataDir, "settlement-proofs.jsonl"),
    fireblocksTransactionsFile: join(dataDir, "fireblocks-transactions.jsonl"),
    deadLetterFile: join(dataDir, "dead-letter.jsonl"),
    idempotencyFile: join(dataDir, "idempotency.json"),
    consumerOffsetsFile: join(dataDir, "consumer-offsets.json"),
    processedEventsFile: join(dataDir, "processed-events.json"),
    webhookNoncesFile: join(dataDir, "webhook-nonces.json"),
    snapshotsDir: join(dataDir, "snapshots"),
    backupsDir: join(dataDir, "backups"),
  };
}

export class EventStore {
  private readonly mutex = new AsyncMutex();
  private postgresCache: DomainEvent[] = [];
  private postgresHydrated = false;

  constructor(
    private readonly filePath: string,
    private readonly replicaPaths: string[] = [],
    private readonly clusterStateFile?: string,
    private readonly postgres = PostgresPersistence.fromEnv(),
  ) {
    this.bootstrapReplicas();
  }

  async append(event: DomainEvent): Promise<DomainEvent> {
    return this.mutex.runExclusive(async () => {
      if (postgresPrimaryMode()) {
        await this.hydrateFromPostgres();
        const persisted = Object.freeze({
          ...event,
          topic: event.topic ?? "exchange.events",
          partition: event.partition ?? partitionFor(event.transactionId),
          offset: event.offset ?? this.postgresCache.length,
          key: event.key ?? event.transactionId,
          payload: Object.freeze({ ...event.payload }),
        });
        await this.requirePostgres().appendEvent(persisted);
        this.postgresCache.push(persisted);
        return persisted;
      }
      const state = this.ensureLeader();
      const activeNodes = state.nodes.filter((node) => node.status === "active");
      if (activeNodes.length < this.quorumSize(state.nodes.length)) {
        throw new Error("Event stream quorum unavailable");
      }
      const leader = this.leaderNode(state);
      const offset = readJsonLines<DomainEvent>(leader.path).length;
      const persisted = Object.freeze({
        ...event,
        topic: event.topic ?? "exchange.events",
        partition: event.partition ?? partitionFor(event.transactionId),
        offset,
        key: event.key ?? event.transactionId,
        payload: Object.freeze({ ...event.payload }),
      });
      appendJsonLine(leader.path, persisted);
      await this.postgres?.appendEvent(persisted);
      for (const node of activeNodes) {
        if (node.nodeId === leader.nodeId) continue;
        this.syncNodeFromLeader(node, leader);
      }
      return persisted;
    });
  }

  all(): DomainEvent[] {
    if (postgresPrimaryMode()) {
      this.assertPostgresHydrated("events");
      return [...this.postgresCache];
    }
    const state = this.ensureLeader();
    return readJsonLines<DomainEvent>(this.leaderNode(state).path);
  }

  byTransaction(transactionId: string): DomainEvent[] {
    return this.all().filter((event) => event.transactionId === transactionId);
  }

  clusterStatus(): Record<string, unknown> {
    if (postgresPrimaryMode()) {
      return {
        mode: "postgres-primary-event-stream",
        sourceOfTruth: "postgres",
        fileFallback: false,
        events: this.postgresCache.length,
        hydrated: this.postgresHydrated,
      };
    }
    const state = this.ensureLeader();
    const leader = this.leaderNode(state);
    const leaderCount = readJsonLines<DomainEvent>(leader.path).length;
    return {
      mode: "deployable-multi-node-file-log",
      epoch: state.epoch,
      leader: {
        nodeId: leader.nodeId,
        events: leaderCount,
        path: leader.path,
        partitions: leader.partitions,
      },
      nodes: state.nodes.map((node) => {
        const events = readJsonLines<DomainEvent>(node.path).length;
        return {
          nodeId: node.nodeId,
          role: node.role,
          status: node.status,
          events,
          inSync: events === leaderCount,
          path: node.path,
          partitions: node.partitions,
          lastHeartbeat: node.lastHeartbeat,
        };
      }),
      partitionReassignment: "round-robin-active-nodes",
      quorum: this.quorumSize(state.nodes.length),
      healthy: state.nodes.filter((node) => node.status === "active").length >= this.quorumSize(state.nodes.length),
    };
  }

  failNode(nodeId: string): ClusterState {
    const state = this.loadClusterState();
    const next = {
      ...state,
      nodes: state.nodes.map((node) => (node.nodeId === nodeId ? { ...node, status: "offline" as const } : node)),
    };
    return this.saveAndElect(next);
  }

  recoverNode(nodeId: string): ClusterState {
    const state = this.ensureLeader();
    const leader = this.leaderNode(state);
    const recovering = state.nodes.find((node) => node.nodeId === nodeId);
    if (!recovering) throw new Error(`Unknown cluster node: ${nodeId}`);
    const marked = {
      ...state,
      nodes: state.nodes.map((node) =>
        node.nodeId === nodeId ? { ...node, status: "recovering" as const, lastHeartbeat: new Date().toISOString() } : node,
      ),
    };
    const node = marked.nodes.find((candidate) => candidate.nodeId === nodeId);
    if (node) this.syncNodeFromLeader(node, leader);
    const recovered = {
      ...marked,
      nodes: marked.nodes.map((nodeState) =>
        nodeState.nodeId === nodeId ? { ...nodeState, status: "active" as const, lastHeartbeat: new Date().toISOString() } : nodeState,
      ),
    };
    return this.saveAndElect(recovered);
  }

  reassignPartitions(): ClusterState {
    return this.saveAndElect(this.assignPartitions(this.loadClusterState()));
  }

  private bootstrapReplicas(): void {
    if (postgresPrimaryMode()) return;
    const state = this.loadClusterState();
    const leader = this.leaderNode(this.saveAndElect(state));
    for (const node of this.loadClusterState().nodes.filter((candidate) => candidate.status === "active")) {
      if (node.nodeId !== leader.nodeId) this.syncNodeFromLeader(node, leader);
    }
  }

  private ensureLeader(): ClusterState {
    return this.saveAndElect(this.loadClusterState());
  }

  private saveAndElect(input: ClusterState): ClusterState {
    const active = input.nodes.filter((node) => node.status === "active");
    const currentLeader = input.nodes.find((node) => node.nodeId === input.leaderId && node.status === "active");
    const elected =
      currentLeader ??
      [...active].sort((left, right) => {
        const countDelta = readJsonLines<DomainEvent>(right.path).length - readJsonLines<DomainEvent>(left.path).length;
        return countDelta || left.nodeId.localeCompare(right.nodeId);
      })[0];
    if (!elected) {
      atomicWriteJson(this.clusterStatePath(), input);
      throw new Error("No active event-stream node available for leader election");
    }
    const withRoles = {
      ...input,
      epoch: input.leaderId === elected.nodeId ? input.epoch : input.epoch + 1,
      leaderId: elected.nodeId,
      nodes: input.nodes.map((node) => ({
        ...node,
        role: node.nodeId === elected.nodeId ? ("leader" as const) : ("follower" as const),
        lastHeartbeat: node.status === "active" ? new Date().toISOString() : node.lastHeartbeat,
      })),
    };
    const assigned = this.assignPartitions(withRoles);
    atomicWriteJson(this.clusterStatePath(), assigned);
    return assigned;
  }

  private loadClusterState(): ClusterState {
    return readJsonFile<ClusterState>(this.clusterStatePath(), this.defaultClusterState());
  }

  private defaultClusterState(): ClusterState {
    const now = new Date().toISOString();
    return this.assignPartitions({
      epoch: 1,
      leaderId: "node-0",
      partitionCount: 32,
      nodes: [
        { nodeId: "node-0", path: this.filePath, role: "leader", status: "active", lastHeartbeat: now, partitions: [] },
        ...this.replicaPaths.map((path, index) => ({
          nodeId: `node-${index + 1}`,
          path,
          role: "follower" as const,
          status: "active" as const,
          lastHeartbeat: now,
          partitions: [],
        })),
      ],
    });
  }

  private assignPartitions(state: ClusterState): ClusterState {
    const active = state.nodes.filter((node) => node.status === "active").sort((left, right) => left.nodeId.localeCompare(right.nodeId));
    return {
      ...state,
      nodes: state.nodes.map((node) => ({
        ...node,
        partitions: active.length === 0 ? [] : partitionsForNode(node.nodeId, active.map((candidate) => candidate.nodeId), state.partitionCount),
      })),
    };
  }

  private leaderNode(state: ClusterState): ClusterNodeState {
    const leader = state.nodes.find((node) => node.nodeId === state.leaderId);
    if (!leader) throw new Error(`Leader ${state.leaderId} is not registered`);
    return leader;
  }

  private syncNodeFromLeader(node: ClusterNodeState, leader: ClusterNodeState): void {
    const leaderEvents = readJsonLines<DomainEvent>(leader.path);
    const followerEvents = readJsonLines<DomainEvent>(node.path);
    if (followerEvents.length > leaderEvents.length) return;
    for (const event of leaderEvents.slice(followerEvents.length)) {
      appendJsonLine(node.path, event);
    }
  }

  private quorumSize(nodes: number): number {
    return Math.floor(nodes / 2) + 1;
  }

  private clusterStatePath(): string {
    return this.clusterStateFile ?? join(this.filePath, "..", "cluster-state.json");
  }

  async hydrateFromPostgres(): Promise<void> {
    if (!postgresPrimaryMode() || this.postgresHydrated) return;
    this.postgresCache = await this.requirePostgres().listEvents();
    this.postgresHydrated = true;
  }

  private assertPostgresHydrated(storeName: string): void {
    if (!this.postgresHydrated) {
      throw new Error(`Postgres-primary ${storeName} store was read before hydration; no file fallback is allowed`);
    }
  }

  private requirePostgres(): PostgresPersistence {
    if (!this.postgres) throw new Error("PERSISTENCE_DRIVER=postgres is required for production event store");
    return this.postgres;
  }
}

export class LedgerStore {
  private readonly mutex = new AsyncMutex();
  private postgresCache: LedgerEntry[] = [];
  private postgresHydrated = false;

  constructor(
    private readonly filePath: string,
    private readonly postgres = PostgresPersistence.fromEnv(),
  ) {}

  async append(input: Omit<LedgerEntry, "entryId" | "timestamp" | "previousHash" | "currentHash">): Promise<LedgerEntry> {
    return this.mutex.runExclusive(async () => {
      if (postgresPrimaryMode()) {
        await this.hydrateFromPostgres();
        const previousHash = this.postgresCache.at(-1)?.currentHash ?? ZERO_HASH;
        const timestamp = new Date().toISOString();
        const entryWithoutHash = {
          ...input,
          entryId: randomUUID(),
          timestamp,
          previousHash,
        };
        const currentHash = hashLedgerEntry(entryWithoutHash);
        const entry: LedgerEntry = Object.freeze({
          ...entryWithoutHash,
          currentHash,
          metadata: Object.freeze({ ...entryWithoutHash.metadata }),
        });
        await this.requirePostgres().appendLedger(entry);
        this.postgresCache.push(entry);
        return entry;
      }
      const entries = this.all();
      const previousHash = entries.at(-1)?.currentHash ?? ZERO_HASH;
      const timestamp = new Date().toISOString();
      const entryWithoutHash = {
        ...input,
        entryId: randomUUID(),
        timestamp,
        previousHash,
      };
      const currentHash = hashLedgerEntry(entryWithoutHash);
      const entry: LedgerEntry = Object.freeze({
        ...entryWithoutHash,
        currentHash,
        metadata: Object.freeze({ ...entryWithoutHash.metadata }),
      });
      appendJsonLine(this.filePath, entry);
      await this.postgres?.appendLedger(entry);
      return entry;
    });
  }

  all(): LedgerEntry[] {
    if (postgresPrimaryMode()) {
      this.assertPostgresHydrated("ledger");
      return [...this.postgresCache];
    }
    return readJsonLines<LedgerEntry>(this.filePath);
  }

  byTransaction(transactionId: string): LedgerEntry[] {
    return this.all().filter((entry) => entry.transactionId === transactionId);
  }

  balance(accountId: string): Record<string, string> {
    const totals = new Map<string, bigint>();
    for (const entry of this.all()) {
      if (entry.accountId !== accountId) continue;
      const current = totals.get(entry.asset) ?? 0n;
      totals.set(entry.asset, current + decimalToUnits(entry.delta));
    }
    return Object.fromEntries([...totals.entries()].map(([asset, units]) => [asset, unitsToDecimal(units)]));
  }

  verifyHashChain(entries = this.all()): { valid: boolean; errors: string[] } {
    const errors: string[] = [];
    let previousHash = ZERO_HASH;
    entries.forEach((entry, index) => {
      if (entry.previousHash !== previousHash) {
        errors.push(`Ledger hash chain break at index ${index}: previousHash mismatch`);
      }
      const recomputed = hashLedgerEntry({
        entryId: entry.entryId,
        eventId: entry.eventId,
        transactionId: entry.transactionId,
        accountId: entry.accountId,
        asset: entry.asset,
        delta: entry.delta,
        amount: entry.amount,
        direction: entry.direction,
        reason: entry.reason,
        metadata: entry.metadata,
        timestamp: entry.timestamp,
        previousHash: entry.previousHash,
      });
      if (entry.currentHash !== recomputed) {
        errors.push(`Ledger hash mismatch at index ${index}`);
      }
      previousHash = entry.currentHash;
    });
    return { valid: errors.length === 0, errors };
  }

  async hydrateFromPostgres(): Promise<void> {
    if (!postgresPrimaryMode() || this.postgresHydrated) return;
    this.postgresCache = await this.requirePostgres().listLedgerEntries();
    this.postgresHydrated = true;
  }

  private assertPostgresHydrated(storeName: string): void {
    if (!this.postgresHydrated) {
      throw new Error(`Postgres-primary ${storeName} store was read before hydration; no file fallback is allowed`);
    }
  }

  private requirePostgres(): PostgresPersistence {
    if (!this.postgres) throw new Error("PERSISTENCE_DRIVER=postgres is required for production ledger store");
    return this.postgres;
  }
}

export class DeadLetterStore {
  constructor(private readonly filePath: string) {}

  append(record: Omit<DeadLetterRecord, "id" | "failedAt">): DeadLetterRecord {
    const deadLetter: DeadLetterRecord = Object.freeze({
      ...record,
      id: randomUUID(),
      failedAt: new Date().toISOString(),
    });
    appendJsonLine(this.filePath, deadLetter);
    return deadLetter;
  }

  all(): DeadLetterRecord[] {
    return readJsonLines<DeadLetterRecord>(this.filePath);
  }
}

export class SettlementProofStore {
  private readonly mutex = new AsyncMutex();
  private postgresCache: SettlementProof[] = [];
  private postgresHydrated = false;

  constructor(
    private readonly filePath: string,
    private readonly postgres = PostgresPersistence.fromEnv(),
  ) {}

  async append(input: Omit<SettlementProof, "proofId" | "timestamp" | "previousHash" | "currentHash">): Promise<SettlementProof> {
    return this.mutex.runExclusive(async () => {
      if (postgresPrimaryMode()) {
        await this.hydrateFromPostgres();
        const previousHash = this.postgresCache.at(-1)?.currentHash ?? ZERO_HASH;
        const timestamp = new Date().toISOString();
        const proofWithoutHash = {
          ...input,
          proofId: randomUUID(),
          timestamp,
          previousHash,
        };
        const currentHash = hashRecord(proofWithoutHash);
        const proof: SettlementProof = Object.freeze({
          ...proofWithoutHash,
          currentHash,
          payload: Object.freeze({ ...proofWithoutHash.payload }),
        });
        await this.requirePostgres().appendSettlementProof(proof);
        this.postgresCache.push(proof);
        return proof;
      }
      const proofs = this.all();
      const previousHash = proofs.at(-1)?.currentHash ?? ZERO_HASH;
      const timestamp = new Date().toISOString();
      const proofWithoutHash = {
        ...input,
        proofId: randomUUID(),
        timestamp,
        previousHash,
      };
      const currentHash = hashRecord(proofWithoutHash);
      const proof: SettlementProof = Object.freeze({
        ...proofWithoutHash,
        currentHash,
        payload: Object.freeze({ ...proofWithoutHash.payload }),
      });
      appendJsonLine(this.filePath, proof);
      await this.postgres?.appendSettlementProof(proof);
      return proof;
    });
  }

  all(): SettlementProof[] {
    if (postgresPrimaryMode()) {
      this.assertPostgresHydrated("settlement proof");
      return [...this.postgresCache];
    }
    return readJsonLines<SettlementProof>(this.filePath);
  }

  byTransaction(transactionId: string): SettlementProof[] {
    return this.all().filter((proof) => proof.transactionId === transactionId);
  }

  latestConfirmed(transactionId: string): SettlementProof | undefined {
    return this.byTransaction(transactionId)
      .filter((proof) => proof.status === "confirmed")
      .at(-1);
  }

  verifyHashChain(entries = this.all()): { valid: boolean; errors: string[] } {
    const errors: string[] = [];
    let previousHash = ZERO_HASH;
    entries.forEach((proof, index) => {
      if (proof.previousHash !== previousHash) {
        errors.push(`Settlement proof hash chain break at index ${index}`);
      }
      const recomputed = hashRecord({
        proofId: proof.proofId,
        transactionId: proof.transactionId,
        settlementId: proof.settlementId,
        txHash: proof.txHash,
        adapter: proof.adapter,
        chainId: proof.chainId,
        status: proof.status,
        requiredConfirmations: proof.requiredConfirmations,
        observedConfirmations: proof.observedConfirmations,
        blockNumber: proof.blockNumber,
        receiptStatus: proof.receiptStatus,
        providerReference: proof.providerReference,
        payload: proof.payload,
        timestamp: proof.timestamp,
        previousHash: proof.previousHash,
      });
      if (proof.currentHash !== recomputed) {
        errors.push(`Settlement proof hash mismatch at index ${index}`);
      }
      previousHash = proof.currentHash;
    });
    return { valid: errors.length === 0, errors };
  }

  async hydrateFromPostgres(): Promise<void> {
    if (!postgresPrimaryMode() || this.postgresHydrated) return;
    this.postgresCache = await this.requirePostgres().listSettlementProofs();
    this.postgresHydrated = true;
  }

  private assertPostgresHydrated(storeName: string): void {
    if (!this.postgresHydrated) {
      throw new Error(`Postgres-primary ${storeName} store was read before hydration; no file fallback is allowed`);
    }
  }

  private requirePostgres(): PostgresPersistence {
    if (!this.postgres) throw new Error("PERSISTENCE_DRIVER=postgres is required for production settlement proof store");
    return this.postgres;
  }
}

export class FireblocksTransactionStore {
  private readonly mutex = new AsyncMutex();
  private postgresCache: FireblocksTransactionRecord[] = [];
  private postgresHydrated = false;

  constructor(
    private readonly filePath: string,
    private readonly postgres = PostgresPersistence.fromEnv(),
  ) {}

  async append(input: Omit<FireblocksTransactionRecord, "recordId" | "timestamp" | "previousHash" | "currentHash">): Promise<FireblocksTransactionRecord> {
    return this.mutex.runExclusive(async () => {
      if (postgresPrimaryMode()) {
        await this.hydrateFromPostgres();
        const previousHash = this.postgresCache.at(-1)?.currentHash ?? ZERO_HASH;
        const timestamp = new Date().toISOString();
        const withoutHash = {
          ...input,
          recordId: randomUUID(),
          timestamp,
          previousHash,
        };
        const currentHash = hashRecord(withoutHash);
        const record: FireblocksTransactionRecord = Object.freeze({
          ...withoutHash,
          currentHash,
          payload: Object.freeze({ ...withoutHash.payload }),
        });
        await this.requirePostgres().appendFireblocksRecord(record);
        this.postgresCache.push(record);
        return record;
      }
      const records = this.all();
      const previousHash = records.at(-1)?.currentHash ?? ZERO_HASH;
      const timestamp = new Date().toISOString();
      const withoutHash = {
        ...input,
        recordId: randomUUID(),
        timestamp,
        previousHash,
      };
      const currentHash = hashRecord(withoutHash);
      const record: FireblocksTransactionRecord = Object.freeze({
        ...withoutHash,
        currentHash,
        payload: Object.freeze({ ...withoutHash.payload }),
      });
      appendJsonLine(this.filePath, record);
      await this.postgres?.appendFireblocksRecord(record);
      return record;
    });
  }

  all(): FireblocksTransactionRecord[] {
    if (postgresPrimaryMode()) {
      this.assertPostgresHydrated("fireblocks transactions");
      return [...this.postgresCache];
    }
    return readJsonLines<FireblocksTransactionRecord>(this.filePath);
  }

  byOrder(orderId: string): FireblocksTransactionRecord[] {
    return this.all().filter((record) => record.orderId === orderId);
  }

  byFireblocksTxId(fireblocksTxId: string): FireblocksTransactionRecord[] {
    return this.all().filter((record) => record.fireblocksTxId === fireblocksTxId);
  }

  verifyHashChain(entries = this.all()): { valid: boolean; errors: string[] } {
    const errors: string[] = [];
    let previousHash = ZERO_HASH;
    entries.forEach((record, index) => {
      if (record.previousHash !== previousHash) {
        errors.push(`Fireblocks transaction hash chain break at index ${index}`);
      }
      const recomputed = hashRecord({
        recordId: record.recordId,
        orderId: record.orderId,
        fireblocksTxId: record.fireblocksTxId,
        fireblocksStatus: record.fireblocksStatus,
        settlementConfirmed: record.settlementConfirmed,
        payoutConfirmed: record.payoutConfirmed,
        settlementAsset: record.settlementAsset,
        settlementAmount: record.settlementAmount,
        destinationWallet: record.destinationWallet,
        liquidityProvider: record.liquidityProvider,
        quoteProvider: record.quoteProvider,
        txHash: record.txHash,
        confirmations: record.confirmations,
        payload: record.payload,
        timestamp: record.timestamp,
        previousHash: record.previousHash,
      });
      if (record.currentHash !== recomputed) {
        errors.push(`Fireblocks transaction hash mismatch at index ${index}`);
      }
      previousHash = record.currentHash;
    });
    return { valid: errors.length === 0, errors };
  }

  async hydrateFromPostgres(): Promise<void> {
    if (!postgresPrimaryMode() || this.postgresHydrated) return;
    this.postgresCache = await this.requirePostgres().listFireblocksRecords();
    this.postgresHydrated = true;
  }

  private assertPostgresHydrated(storeName: string): void {
    if (!this.postgresHydrated) {
      throw new Error(`Postgres-primary ${storeName} store was read before hydration; no file fallback is allowed`);
    }
  }

  private requirePostgres(): PostgresPersistence {
    if (!this.postgres) throw new Error("PERSISTENCE_DRIVER=postgres is required for production Fireblocks transaction store");
    return this.postgres;
  }
}

export class IdempotencyStore {
  private readonly mutex = new AsyncMutex();

  constructor(private readonly filePath: string) {}

  get<T>(scope: string, key: string): T | undefined {
    const responses = readJsonFile<Record<string, unknown>>(this.filePath, {});
    return responses[`${scope}:${key}`] as T | undefined;
  }

  async set<T>(scope: string, key: string, response: T): Promise<T> {
    return this.mutex.runExclusive(async () => {
      const responses = readJsonFile<Record<string, unknown>>(this.filePath, {});
      responses[`${scope}:${key}`] = response;
      atomicWriteJson(this.filePath, responses);
      return response;
    });
  }
}

export class ConsumerOffsetStore {
  private readonly mutex = new AsyncMutex();

  constructor(private readonly filePath: string) {}

  get(groupName: string): number {
    const offsets = readJsonFile<Record<string, number>>(this.filePath, {});
    return offsets[storageScopedKey(groupName)] ?? -1;
  }

  async set(groupName: string, offset: number): Promise<void> {
    await this.mutex.runExclusive(async () => {
      const offsets = readJsonFile<Record<string, number>>(this.filePath, {});
      offsets[storageScopedKey(groupName)] = offset;
      atomicWriteJson(this.filePath, offsets);
    });
  }
}

export class ProcessedEventStore {
  private readonly mutex = new AsyncMutex();

  constructor(private readonly filePath: string) {}

  has(consumerGroup: string, eventId: string): boolean {
    const processed = readJsonFile<Record<string, boolean>>(this.filePath, {});
    return Boolean(processed[storageScopedKey(`${consumerGroup}:${eventId}`)]);
  }

  async mark(consumerGroup: string, eventId: string): Promise<void> {
    await this.mutex.runExclusive(async () => {
      const processed = readJsonFile<Record<string, boolean>>(this.filePath, {});
      processed[storageScopedKey(`${consumerGroup}:${eventId}`)] = true;
      atomicWriteJson(this.filePath, processed);
    });
  }
}

export class ReplayNonceStore {
  private readonly mutex = new AsyncMutex();

  constructor(private readonly filePath: string) {}

  has(nonce: string): boolean {
    const nonces = readJsonFile<Record<string, string>>(this.filePath, {});
    return Boolean(nonces[nonce]);
  }

  async remember(nonce: string): Promise<void> {
    await this.mutex.runExclusive(async () => {
      const nonces = readJsonFile<Record<string, string>>(this.filePath, {});
      nonces[nonce] = new Date().toISOString();
      atomicWriteJson(this.filePath, nonces);
    });
  }
}

export class ExchangeStore {
  readonly paths: StorePaths;
  readonly events: EventStore;
  readonly ledger: LedgerStore;
  readonly settlementProofs: SettlementProofStore;
  readonly fireblocksTransactions: FireblocksTransactionStore;
  readonly deadLetters: DeadLetterStore;
  readonly idempotency: IdempotencyStore;
  readonly consumerOffsets: ConsumerOffsetStore;
  readonly processedEvents: ProcessedEventStore;
  readonly webhookNonces: ReplayNonceStore;
  readonly postgres?: PostgresPersistence;

  constructor(dataDir?: string) {
    this.paths = defaultStorePaths(dataDir);
    this.postgres = PostgresPersistence.fromEnv();
    ensureDir(this.paths.dataDir);
    ensureDir(this.paths.snapshotsDir);
    ensureDir(this.paths.backupsDir);
    this.events = new EventStore(this.paths.eventsFile, this.paths.replicaEventFiles, this.paths.clusterStateFile, this.postgres);
    this.ledger = new LedgerStore(this.paths.ledgerFile, this.postgres);
    this.settlementProofs = new SettlementProofStore(this.paths.settlementProofsFile, this.postgres);
    this.fireblocksTransactions = new FireblocksTransactionStore(this.paths.fireblocksTransactionsFile, this.postgres);
    this.deadLetters = new DeadLetterStore(this.paths.deadLetterFile);
    this.idempotency = new IdempotencyStore(this.paths.idempotencyFile);
    this.consumerOffsets = new ConsumerOffsetStore(this.paths.consumerOffsetsFile);
    this.processedEvents = new ProcessedEventStore(this.paths.processedEventsFile);
    this.webhookNonces = new ReplayNonceStore(this.paths.webhookNoncesFile);
  }

  async postgresStatus(): Promise<Record<string, unknown>> {
    return this.postgres ? this.postgres.verify() : { enabled: false };
  }

  async ready(): Promise<void> {
    if (!postgresPrimaryMode()) return;
    if (!this.postgres) throw new Error("Production mode requires PERSISTENCE_DRIVER=postgres and a valid Neon DATABASE_URL");
    await this.postgres.verify();
    await this.events.hydrateFromPostgres();
    await this.ledger.hydrateFromPostgres();
    await this.settlementProofs.hydrateFromPostgres();
    await this.fireblocksTransactions.hydrateFromPostgres();
  }
}

export function decimalToUnits(value: string, scale = 8): bigint {
  const normalized = String(value).trim();
  if (!/^-?\d+(\.\d+)?$/.test(normalized)) {
    throw new Error(`Invalid decimal amount: ${value}`);
  }
  const negative = normalized.startsWith("-");
  const unsigned = negative ? normalized.slice(1) : normalized;
  const [whole, fraction = ""] = unsigned.split(".");
  const units = BigInt(`${whole}${fraction.padEnd(scale, "0").slice(0, scale)}`);
  return negative ? -units : units;
}

export function unitsToDecimal(units: bigint, scale = 8): string {
  const negative = units < 0n;
  const absolute = negative ? -units : units;
  const divisor = 10n ** BigInt(scale);
  const whole = absolute / divisor;
  const fraction = (absolute % divisor).toString().padStart(scale, "0").replace(/0+$/, "");
  return `${negative ? "-" : ""}${whole.toString()}${fraction ? `.${fraction}` : ""}`;
}

function partitionFor(transactionId: string, partitions = 32): number {
  const digest = createHash("sha256").update(transactionId).digest();
  return digest.readUInt32BE(0) % partitions;
}

function partitionsForNode(nodeId: string, activeNodeIds: string[], partitionCount: number): number[] {
  const activeIndex = activeNodeIds.indexOf(nodeId);
  if (activeIndex === -1) return [];
  const partitions: number[] = [];
  for (let partition = 0; partition < partitionCount; partition += 1) {
    if (partition % activeNodeIds.length === activeIndex) partitions.push(partition);
  }
  return partitions;
}

function postgresPrimaryMode(): boolean {
  return process.env.PERSISTENCE_DRIVER === "postgres" && String(process.env.BLOCKCHAIN_EXECUTION_MODE ?? "").toLowerCase() === "real";
}

function storageScopedKey(key: string): string {
  return `${postgresPrimaryMode() ? "postgres-primary" : "file-log"}:${key}`;
}

function hashLedgerEntry(value: Record<string, unknown>): string {
  return hashRecord(value);
}

function hashRecord(value: Record<string, unknown>): string {
  return createHash("sha256").update(stableStringify(value)).digest("hex");
}

function stableStringify(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map((item) => stableStringify(item)).join(",")}]`;
  const record = value as Record<string, unknown>;
  return `{${Object.keys(record)
    .filter((key) => record[key] !== undefined)
    .sort()
    .map((key) => `${JSON.stringify(key)}:${stableStringify(record[key])}`)
    .join(",")}}`;
}
