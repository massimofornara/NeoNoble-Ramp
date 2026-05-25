import type { DomainEvent, FireblocksTransactionRecord, LedgerEntry, SettlementProof } from "./types.js";

type PoolLike = {
  query(sql: string, params?: unknown[]): Promise<{ rows: Array<Record<string, unknown>> }>;
};

export class PostgresPersistence {
  private schemaReady = false;

  private constructor(private readonly pool: PoolLike) {}

  static fromEnv(): PostgresPersistence | undefined {
    if (process.env.PERSISTENCE_DRIVER !== "postgres") return undefined;
    if (!process.env.DATABASE_URL) {
      throw new Error("PERSISTENCE_DRIVER=postgres requires DATABASE_URL");
    }
    assertProductionDatabaseUrl(process.env.DATABASE_URL);
    return new PostgresPersistence(createPool(process.env.DATABASE_URL));
  }

  async appendEvent(event: DomainEvent): Promise<void> {
    await this.ensureSchema();
    await this.pool.query(
      `insert into exchange_events(event_id, event_type, transaction_id, event_ts, topic, partition_id, offset_id, event_key, payload)
       values ($1,$2,$3,$4,$5,$6,$7,$8,$9)
       on conflict (event_id) do nothing`,
      [
        event.eventId,
        event.type,
        event.transactionId,
        event.timestamp,
        event.topic ?? "exchange.events",
        event.partition ?? null,
        event.offset ?? null,
        event.key ?? event.transactionId,
        event.payload,
      ],
    );
  }

  async appendLedger(entry: LedgerEntry): Promise<void> {
    await this.ensureSchema();
    await this.pool.query(
      `insert into ledger_entries(entry_id, event_id, transaction_id, account_id, asset, delta, amount, direction, reason, metadata, entry_ts, previous_hash, current_hash)
       values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)
       on conflict (entry_id) do nothing`,
      [
        entry.entryId,
        entry.eventId,
        entry.transactionId,
        entry.accountId,
        entry.asset,
        entry.delta,
        entry.amount,
        entry.direction,
        entry.reason,
        entry.metadata,
        entry.timestamp,
        entry.previousHash,
        entry.currentHash,
      ],
    );
  }

  async appendSettlementProof(proof: SettlementProof): Promise<void> {
    await this.ensureSchema();
    await this.pool.query(
      `insert into settlement_proofs(proof_id, transaction_id, settlement_id, tx_hash, adapter, chain_id, status, required_confirmations,
       observed_confirmations, block_number, receipt_status, provider_reference, payload, proof_ts, previous_hash, current_hash)
       values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
       on conflict (proof_id) do nothing`,
      [
        proof.proofId,
        proof.transactionId,
        proof.settlementId,
        proof.txHash,
        proof.adapter,
        proof.chainId,
        proof.status,
        proof.requiredConfirmations,
        proof.observedConfirmations,
        proof.blockNumber ?? null,
        proof.receiptStatus ?? null,
        proof.providerReference ?? null,
        proof.payload,
        proof.timestamp,
        proof.previousHash,
        proof.currentHash,
      ],
    );
  }

  async appendFireblocksRecord(record: FireblocksTransactionRecord): Promise<void> {
    await this.ensureSchema();
    await this.pool.query(
      `insert into fireblocks_transactions(record_id, order_id, fireblocks_tx_id, fireblocks_status, settlement_confirmed,
       payout_confirmed, settlement_asset, settlement_amount, destination_wallet, liquidity_provider, quote_provider, tx_hash,
       confirmations, payload, record_ts, previous_hash, current_hash)
       values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17)
       on conflict (record_id) do nothing`,
      [
        record.recordId,
        record.orderId,
        record.fireblocksTxId,
        record.fireblocksStatus,
        record.settlementConfirmed,
        record.payoutConfirmed,
        record.settlementAsset,
        record.settlementAmount,
        record.destinationWallet,
        record.liquidityProvider ?? null,
        record.quoteProvider ?? null,
        record.txHash ?? null,
        record.confirmations,
        record.payload,
        record.timestamp,
        record.previousHash,
        record.currentHash,
      ],
    );
  }

  async verify(): Promise<Record<string, unknown>> {
    await this.ensureSchema();
    const events = await this.pool.query("select count(*)::int as count from exchange_events");
    const ledger = await this.pool.query("select count(*)::int as count from ledger_entries");
    const proofs = await this.pool.query("select count(*)::int as count from settlement_proofs");
    const fireblocks = await this.pool.query("select count(*)::int as count from fireblocks_transactions");
    return {
      enabled: true,
      events: events.rows[0]?.count ?? 0,
      ledgerEntries: ledger.rows[0]?.count ?? 0,
      settlementProofs: proofs.rows[0]?.count ?? 0,
      fireblocksTransactions: fireblocks.rows[0]?.count ?? 0,
      walReplication: "use PostgreSQL WAL/streaming replication at the database layer",
    };
  }

  async listEvents(): Promise<DomainEvent[]> {
    await this.ensureSchema();
    const result = await this.pool.query(
      `select event_id, event_type, transaction_id, event_ts, topic, partition_id, offset_id, event_key, payload
       from exchange_events
       order by offset_id asc, inserted_at asc`,
    );
    return result.rows.map((row) => ({
      eventId: String(row.event_id),
      type: row.event_type as DomainEvent["type"],
      transactionId: String(row.transaction_id),
      timestamp: timestampIso(row.event_ts),
      topic: String(row.topic),
      partition: row.partition_id === null || row.partition_id === undefined ? undefined : Number(row.partition_id),
      offset: row.offset_id === null || row.offset_id === undefined ? undefined : Number(row.offset_id),
      key: row.event_key === null || row.event_key === undefined ? undefined : String(row.event_key),
      payload: asRecord(row.payload),
    }));
  }

  async listLedgerEntries(): Promise<LedgerEntry[]> {
    await this.ensureSchema();
    const result = await this.pool.query(
      `select entry_id, event_id, transaction_id, account_id, asset, delta, amount, direction, reason, metadata,
              entry_ts, previous_hash, current_hash
       from ledger_entries
       order by entry_ts asc, inserted_at asc`,
    );
    return result.rows.map((row) => ({
      entryId: String(row.entry_id),
      eventId: String(row.event_id),
      transactionId: String(row.transaction_id),
      accountId: String(row.account_id),
      asset: String(row.asset),
      delta: decimalText(row.delta),
      amount: decimalText(row.amount),
      direction: row.direction === "debit" ? "debit" : "credit",
      reason: String(row.reason),
      metadata: asRecord(row.metadata),
      timestamp: timestampIso(row.entry_ts),
      previousHash: String(row.previous_hash),
      currentHash: String(row.current_hash),
    }));
  }

  async listSettlementProofs(): Promise<SettlementProof[]> {
    await this.ensureSchema();
    const result = await this.pool.query(
      `select proof_id, transaction_id, settlement_id, tx_hash, adapter, chain_id, status, required_confirmations,
              observed_confirmations, block_number, receipt_status, provider_reference, payload, proof_ts,
              previous_hash, current_hash
       from settlement_proofs
       order by proof_ts asc, inserted_at asc`,
    );
    return result.rows.map((row) => ({
      proofId: String(row.proof_id),
      transactionId: String(row.transaction_id),
      settlementId: String(row.settlement_id),
      txHash: String(row.tx_hash),
      adapter: row.adapter as SettlementProof["adapter"],
      chainId: Number(row.chain_id),
      status: row.status === "confirmed" ? "confirmed" : "initiated",
      requiredConfirmations: Number(row.required_confirmations),
      observedConfirmations: Number(row.observed_confirmations),
      blockNumber: row.block_number === null || row.block_number === undefined ? undefined : Number(row.block_number),
      receiptStatus: row.receipt_status as SettlementProof["receiptStatus"],
      providerReference: row.provider_reference === null || row.provider_reference === undefined ? undefined : String(row.provider_reference),
      payload: asRecord(row.payload),
      timestamp: timestampIso(row.proof_ts),
      previousHash: String(row.previous_hash),
      currentHash: String(row.current_hash),
    }));
  }

  async listFireblocksRecords(): Promise<FireblocksTransactionRecord[]> {
    await this.ensureSchema();
    const result = await this.pool.query(
      `select record_id, order_id, fireblocks_tx_id, fireblocks_status, settlement_confirmed, payout_confirmed,
              settlement_asset, settlement_amount, destination_wallet, liquidity_provider, quote_provider, tx_hash,
              confirmations, payload, record_ts, previous_hash, current_hash
       from fireblocks_transactions
       order by record_ts asc, inserted_at asc`,
    );
    return result.rows.map((row) => ({
      recordId: String(row.record_id),
      orderId: String(row.order_id),
      fireblocksTxId: String(row.fireblocks_tx_id),
      fireblocksStatus: String(row.fireblocks_status),
      settlementConfirmed: Boolean(row.settlement_confirmed),
      payoutConfirmed: Boolean(row.payout_confirmed),
      settlementAsset: String(row.settlement_asset),
      settlementAmount: decimalText(row.settlement_amount),
      destinationWallet: String(row.destination_wallet),
      liquidityProvider: row.liquidity_provider === null || row.liquidity_provider === undefined ? undefined : String(row.liquidity_provider),
      quoteProvider: row.quote_provider === null || row.quote_provider === undefined ? undefined : String(row.quote_provider),
      txHash: row.tx_hash === null || row.tx_hash === undefined ? undefined : String(row.tx_hash),
      confirmations: Number(row.confirmations),
      payload: asRecord(row.payload),
      timestamp: timestampIso(row.record_ts),
      previousHash: String(row.previous_hash),
      currentHash: String(row.current_hash),
    }));
  }

  private async ensureSchema(): Promise<void> {
    if (this.schemaReady) return;
    await this.pool.query(SQL_SCHEMA);
    this.schemaReady = true;
  }
}

function createPool(databaseUrl: string): PoolLike {
  const dynamicRequire = new Function("specifier", "return import(specifier)") as (specifier: string) => Promise<{ Pool: new (config: Record<string, unknown>) => PoolLike }>;
  let pool: PoolLike | undefined;
  return {
    async query(sql: string, params?: unknown[]) {
      if (!pool) {
        const pg = await dynamicRequire("pg");
        const parsed = new URL(databaseUrl);
        pool = new pg.Pool({
          connectionString: databaseUrl,
          ...(parsed.searchParams.get("sslmode") === "require" ? { ssl: { rejectUnauthorized: true } } : {}),
        });
      }
      return pool.query(sql, params);
    },
  };
}

function assertProductionDatabaseUrl(databaseUrl: string): void {
  if (String(process.env.BLOCKCHAIN_EXECUTION_MODE ?? "").toLowerCase() !== "real") return;
  let parsed: URL;
  try {
    parsed = new URL(databaseUrl);
  } catch {
    throw new Error("DATABASE_URL must be a valid PostgreSQL URL");
  }
  if (!["postgresql:", "postgres:"].includes(parsed.protocol)) {
    throw new Error("DATABASE_URL must use postgresql:// or postgres://");
  }
  const host = parsed.hostname.toLowerCase();
  if (!host || ["postgres", "localhost", "127.0.0.1", "::1"].includes(host)) {
    throw new Error("Production DATABASE_URL must not point to localhost or docker hostname postgres");
  }
  if (!host.endsWith(".neon.tech")) {
    throw new Error("Production DATABASE_URL must point to a Neon host ending in .neon.tech");
  }
  if (parsed.searchParams.get("sslmode") !== "require") {
    throw new Error("Production DATABASE_URL must include sslmode=require");
  }
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function decimalText(value: unknown): string {
  const text = String(value);
  return text.includes(".") ? text.replace(/\.?0+$/, "") : text;
}

function timestampIso(value: unknown): string {
  if (value instanceof Date) return value.toISOString();
  return new Date(String(value)).toISOString();
}

const SQL_SCHEMA = `
create table if not exists exchange_events (
  event_id uuid primary key,
  event_type text not null,
  transaction_id text not null,
  event_ts timestamptz not null,
  topic text not null,
  partition_id integer,
  offset_id bigint,
  event_key text,
  payload jsonb not null,
  inserted_at timestamptz not null default now()
);

create unique index if not exists exchange_events_topic_partition_offset_uq
on exchange_events(topic, partition_id, offset_id)
where partition_id is not null and offset_id is not null;

create table if not exists ledger_entries (
  entry_id uuid primary key,
  event_id uuid not null,
  transaction_id text not null,
  account_id text not null,
  asset text not null,
  delta numeric(38, 18) not null,
  amount numeric(38, 18) not null,
  direction text not null check (direction in ('debit', 'credit')),
  reason text not null,
  metadata jsonb not null,
  entry_ts timestamptz not null,
  previous_hash text not null,
  current_hash text not null,
  inserted_at timestamptz not null default now()
);

create table if not exists settlement_proofs (
  proof_id uuid primary key,
  transaction_id text not null,
  settlement_id text not null,
  tx_hash text not null,
  adapter text not null,
  chain_id integer not null,
  status text not null,
  required_confirmations integer not null,
  observed_confirmations integer not null,
  block_number bigint,
  receipt_status text,
  provider_reference text,
  payload jsonb not null,
  proof_ts timestamptz not null,
  previous_hash text not null,
  current_hash text not null,
  inserted_at timestamptz not null default now()
);

create table if not exists fireblocks_transactions (
  record_id uuid primary key,
  order_id text not null,
  fireblocks_tx_id text not null,
  fireblocks_status text not null,
  settlement_confirmed boolean not null,
  payout_confirmed boolean not null,
  settlement_asset text not null,
  settlement_amount numeric(38, 18) not null,
  destination_wallet text not null,
  liquidity_provider text,
  quote_provider text,
  tx_hash text,
  confirmations integer not null,
  payload jsonb not null,
  record_ts timestamptz not null,
  previous_hash text not null,
  current_hash text not null,
  inserted_at timestamptz not null default now()
);

create table if not exists replay_snapshots (
  snapshot_id uuid primary key,
  event_offset bigint not null,
  snapshot jsonb not null,
  created_at timestamptz not null default now()
);

create or replace function prevent_update_delete()
returns trigger language plpgsql as $$
begin
  raise exception 'append-only table cannot be updated or deleted';
end;
$$;

drop trigger if exists exchange_events_append_only_update on exchange_events;
create trigger exchange_events_append_only_update before update or delete on exchange_events
for each row execute function prevent_update_delete();

drop trigger if exists ledger_entries_append_only_update on ledger_entries;
create trigger ledger_entries_append_only_update before update or delete on ledger_entries
for each row execute function prevent_update_delete();

drop trigger if exists settlement_proofs_append_only_update on settlement_proofs;
create trigger settlement_proofs_append_only_update before update or delete on settlement_proofs
for each row execute function prevent_update_delete();

drop trigger if exists fireblocks_transactions_append_only_update on fireblocks_transactions;
create trigger fireblocks_transactions_append_only_update before update or delete on fireblocks_transactions
for each row execute function prevent_update_delete();
`;
