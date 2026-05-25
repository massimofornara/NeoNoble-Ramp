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
