create extension if not exists "pgcrypto";

do $$ begin
  create type account_type as enum ('USER', 'EXCHANGE_RESERVE', 'FEE_REVENUE', 'CLEARING', 'LIQUIDITY_POOL', 'RISK_RESERVE');
exception when duplicate_object then null; end $$;

do $$ begin
  create type normal_balance as enum ('DEBIT', 'CREDIT');
exception when duplicate_object then null; end $$;

do $$ begin
  create type ledger_direction as enum ('DEBIT', 'CREDIT');
exception when duplicate_object then null; end $$;

do $$ begin
  create type global_transaction_state as enum ('CREATED', 'PENDING', 'PROCESSING', 'SETTLED', 'FAILED', 'REVERSED');
exception when duplicate_object then null; end $$;

do $$ begin
  create type order_type as enum ('MARKET', 'LIMIT');
exception when duplicate_object then null; end $$;

do $$ begin
  create type order_side as enum ('BUY', 'SELL');
exception when duplicate_object then null; end $$;

create table if not exists accounts (
  id uuid primary key default gen_random_uuid(),
  owner_id text,
  account_type account_type not null,
  asset text not null,
  normal_balance normal_balance not null,
  allow_overdraft boolean not null default false,
  status text not null default 'ACTIVE',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists accounts_owner_type_asset_idx on accounts(coalesce(owner_id, 'SYSTEM'), account_type, asset);
create index if not exists accounts_owner_idx on accounts(owner_id);
create index if not exists accounts_asset_idx on accounts(asset);

create table if not exists balances (
  account_id uuid not null references accounts(id),
  asset text not null,
  available numeric(38, 18) not null default 0,
  held numeric(38, 18) not null default 0,
  version bigint not null default 0,
  updated_at timestamptz not null default now(),
  primary key (account_id, asset),
  constraint balances_non_negative check (available >= 0 and held >= 0)
);

create table if not exists ledger_transactions (
  id uuid primary key default gen_random_uuid(),
  idempotency_key text not null unique,
  correlation_id text not null,
  transaction_type text not null,
  state global_transaction_state not null default 'CREATED',
  external_provider text,
  external_id text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists ledger_transactions_state_idx on ledger_transactions(state);
create index if not exists ledger_transactions_external_idx on ledger_transactions(external_provider, external_id);
create index if not exists ledger_transactions_correlation_idx on ledger_transactions(correlation_id);

create table if not exists journal_entries (
  id uuid primary key default gen_random_uuid(),
  ledger_transaction_id uuid not null references ledger_transactions(id),
  account_id uuid not null references accounts(id),
  asset text not null,
  direction ledger_direction not null,
  amount numeric(38, 18) not null check (amount > 0),
  entry_index integer not null,
  memo text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (ledger_transaction_id, entry_index)
);

create index if not exists journal_entries_account_idx on journal_entries(account_id, created_at desc);
create index if not exists journal_entries_ledger_idx on journal_entries(ledger_transaction_id);

create table if not exists holds (
  id uuid primary key default gen_random_uuid(),
  account_id uuid not null references accounts(id),
  asset text not null,
  amount numeric(38, 18) not null check (amount > 0),
  reason text not null,
  idempotency_key text not null unique,
  status text not null default 'ACTIVE',
  correlation_id text not null,
  expires_at timestamptz,
  released_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists holds_account_status_idx on holds(account_id, status);
create index if not exists holds_expires_idx on holds(expires_at) where status = 'ACTIVE';

create table if not exists settlements (
  id uuid primary key default gen_random_uuid(),
  ledger_transaction_id uuid references ledger_transactions(id),
  settlement_type text not null,
  provider text,
  provider_reference text,
  state global_transaction_state not null default 'CREATED',
  amount numeric(38, 18),
  asset text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists settlements_provider_idx on settlements(provider, provider_reference);
create index if not exists settlements_state_idx on settlements(state);

create table if not exists transaction_events (
  id uuid primary key default gen_random_uuid(),
  ledger_transaction_id uuid references ledger_transactions(id),
  aggregate_id text not null,
  event_type text not null,
  previous_state global_transaction_state,
  next_state global_transaction_state,
  correlation_id text not null,
  idempotency_key text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists transaction_events_aggregate_idx on transaction_events(aggregate_id, created_at);
create index if not exists transaction_events_type_idx on transaction_events(event_type, created_at desc);

create table if not exists exchange_orders (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  order_type order_type not null,
  side order_side not null,
  base_asset text not null,
  quote_asset text not null,
  amount numeric(38, 18) not null check (amount > 0),
  limit_price numeric(38, 18),
  max_slippage_bps integer not null default 100,
  state global_transaction_state not null default 'CREATED',
  ledger_transaction_id uuid references ledger_transactions(id),
  idempotency_key text not null unique,
  correlation_id text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists exchange_orders_user_idx on exchange_orders(user_id, created_at desc);
create index if not exists exchange_orders_pair_idx on exchange_orders(base_asset, quote_asset, state);

create table if not exists swap_executions (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references exchange_orders(id),
  user_id text not null,
  from_asset text not null,
  to_asset text not null,
  amount_in numeric(38, 18) not null,
  amount_out numeric(38, 18) not null,
  execution_price numeric(38, 18) not null,
  spread_bps integer not null,
  slippage_bps integer not null,
  route jsonb not null,
  ledger_transaction_id uuid references ledger_transactions(id),
  created_at timestamptz not null default now()
);

create table if not exists liquidity_pools (
  id uuid primary key default gen_random_uuid(),
  base_asset text not null,
  quote_asset text not null,
  base_depth numeric(38, 18) not null default 0,
  quote_depth numeric(38, 18) not null default 0,
  spread_bps integer not null default 50,
  enabled boolean not null default true,
  metadata jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  unique (base_asset, quote_asset)
);

create table if not exists oracle_prices (
  id uuid primary key default gen_random_uuid(),
  base_asset text not null,
  quote_asset text not null,
  price numeric(38, 18) not null check (price > 0),
  source text not null,
  confidence_bps integer not null default 10000,
  observed_at timestamptz not null default now(),
  unique (base_asset, quote_asset, source, observed_at)
);

create index if not exists oracle_prices_latest_idx on oracle_prices(base_asset, quote_asset, observed_at desc);

create table if not exists risk_events (
  id uuid primary key default gen_random_uuid(),
  user_id text,
  wallet_address text,
  risk_type text not null,
  severity text not null,
  score integer not null,
  blocked boolean not null default false,
  correlation_id text not null,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index if not exists risk_events_user_idx on risk_events(user_id, created_at desc);
create index if not exists risk_events_blocked_idx on risk_events(blocked, created_at desc);

create table if not exists immutable_audit_log (
  id uuid primary key default gen_random_uuid(),
  actor_id text,
  action text not null,
  resource_type text not null,
  resource_id text not null,
  correlation_id text not null,
  payload jsonb not null default '{}'::jsonb,
  previous_hash text,
  event_hash text not null,
  created_at timestamptz not null default now()
);

create index if not exists immutable_audit_log_resource_idx on immutable_audit_log(resource_type, resource_id, created_at desc);

create table if not exists encrypted_pii (
  id uuid primary key default gen_random_uuid(),
  owner_id text not null,
  pii_type text not null,
  ciphertext text not null,
  key_version text not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists encrypted_pii_owner_type_idx on encrypted_pii(owner_id, pii_type);

insert into liquidity_pools(base_asset, quote_asset, base_depth, quote_depth, spread_bps, metadata)
values
  ('NENO', 'USDC', 1000000, 1000000, 75, '{"bootstrap": true}'),
  ('NENO', 'ETH', 1000000, 500, 90, '{"bootstrap": true}')
on conflict (base_asset, quote_asset) do nothing;

insert into oracle_prices(base_asset, quote_asset, price, source, confidence_bps)
values
  ('NENO', 'USDC', 1, 'bootstrap', 8000),
  ('NENO', 'ETH', 0.0003, 'bootstrap', 7000)
on conflict do nothing;
