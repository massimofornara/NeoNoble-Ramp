create extension if not exists "pgcrypto";

do $$ begin create type wallet_tier as enum ('HOT', 'WARM', 'COLD'); exception when duplicate_object then null; end $$;
do $$ begin create type custody_wallet_status as enum ('ACTIVE', 'DISABLED', 'ROTATING', 'COMPROMISED'); exception when duplicate_object then null; end $$;
do $$ begin create type key_purpose as enum ('WITHDRAWAL_SIGNING', 'DEPOSIT_ADDRESS', 'AUDIT_LOG', 'SECRET_ENCRYPTION'); exception when duplicate_object then null; end $$;
do $$ begin create type approval_state as enum ('REQUESTED', 'APPROVED', 'REJECTED', 'EXPIRED'); exception when duplicate_object then null; end $$;
do $$ begin create type withdrawal_state as enum ('CREATED', 'RISK_REVIEW', 'APPROVAL_REQUIRED', 'APPROVED', 'SIGNED', 'BROADCAST_READY', 'COMPLETED', 'FAILED', 'CANCELLED'); exception when duplicate_object then null; end $$;
do $$ begin create type clob_order_type as enum ('MARKET', 'LIMIT', 'STOP'); exception when duplicate_object then null; end $$;
do $$ begin create type clob_order_side as enum ('BUY', 'SELL'); exception when duplicate_object then null; end $$;
do $$ begin create type clob_order_state as enum ('CREATED', 'OPEN', 'PARTIALLY_FILLED', 'FILLED', 'CANCELLED'); exception when duplicate_object then null; end $$;
do $$ begin create type time_in_force as enum ('GTC', 'IOC', 'FOK'); exception when duplicate_object then null; end $$;

create table if not exists kms_keys (
  id uuid primary key default gen_random_uuid(),
  key_alias text not null,
  key_version integer not null,
  purpose key_purpose not null,
  provider text not null,
  public_key text,
  encrypted_private_material text,
  status text not null default 'ACTIVE',
  rotation_due_at timestamptz,
  created_at timestamptz not null default now(),
  unique(key_alias, key_version)
);

create table if not exists custody_wallets (
  id uuid primary key default gen_random_uuid(),
  asset text not null,
  chain text not null,
  tier wallet_tier not null,
  status custody_wallet_status not null default 'ACTIVE',
  kms_key_id uuid references kms_keys(id),
  max_online_balance numeric(38, 18) not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(asset, chain, tier)
);

create table if not exists custody_addresses (
  id uuid primary key default gen_random_uuid(),
  wallet_id uuid not null references custody_wallets(id),
  owner_id text,
  address text not null,
  derivation_path text,
  whitelisted boolean not null default false,
  whitelist_expires_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(address, wallet_id)
);

create table if not exists address_whitelist (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  asset text not null,
  chain text not null,
  address text not null,
  label text,
  status text not null default 'PENDING',
  approved_by text,
  approved_at timestamptz,
  cooldown_until timestamptz not null default now() + interval '24 hours',
  created_at timestamptz not null default now(),
  unique(user_id, asset, chain, address)
);

create table if not exists withdrawal_requests (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  asset text not null,
  chain text not null,
  amount numeric(38,18) not null check(amount > 0),
  destination_address text not null,
  state withdrawal_state not null default 'CREATED',
  risk_score integer not null default 0,
  idempotency_key text not null unique,
  correlation_id text not null,
  hold_id uuid,
  ledger_transaction_id uuid references ledger_transactions(id),
  signed_payload text,
  tx_hash text,
  failure_reason text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists withdrawal_requests_user_idx on withdrawal_requests(user_id, created_at desc);
create index if not exists withdrawal_requests_state_idx on withdrawal_requests(state);

create table if not exists multisig_policies (
  id uuid primary key default gen_random_uuid(),
  scope text not null,
  asset text,
  chain text,
  threshold integer not null check(threshold > 0),
  approvers text[] not null,
  amount_threshold numeric(38,18) not null default 0,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists multisig_approvals (
  id uuid primary key default gen_random_uuid(),
  request_type text not null,
  request_id uuid not null,
  approver_id text not null,
  state approval_state not null default 'REQUESTED',
  signature text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(request_type, request_id, approver_id)
);

create table if not exists clob_markets (
  market text primary key,
  base_asset text not null,
  quote_asset text not null,
  tick_size numeric(38,18) not null,
  lot_size numeric(38,18) not null,
  min_notional numeric(38,18) not null default 0,
  status text not null default 'ONLINE',
  maker_fee_bps integer not null default 10,
  taker_fee_bps integer not null default 20,
  created_at timestamptz not null default now()
);

create table if not exists clob_orders (
  id uuid primary key default gen_random_uuid(),
  user_id text not null,
  market text not null references clob_markets(market),
  side clob_order_side not null,
  order_type clob_order_type not null,
  order_state clob_order_state not null default 'CREATED',
  quantity numeric(38,18) not null check(quantity > 0),
  remaining_quantity numeric(38,18) not null check(remaining_quantity >= 0),
  price numeric(38,18),
  stop_price numeric(38,18),
  time_in_force time_in_force not null default 'GTC',
  sequence bigint generated always as identity,
  hold_id uuid,
  idempotency_key text not null unique,
  correlation_id text not null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists clob_orders_book_idx on clob_orders(market, side, order_state, price, sequence);
create index if not exists clob_orders_user_idx on clob_orders(user_id, created_at desc);

create table if not exists clob_trades (
  id uuid primary key default gen_random_uuid(),
  market text not null references clob_markets(market),
  maker_order_id uuid not null references clob_orders(id),
  taker_order_id uuid not null references clob_orders(id),
  maker_user_id text not null,
  taker_user_id text not null,
  price numeric(38,18) not null,
  quantity numeric(38,18) not null,
  maker_fee numeric(38,18) not null,
  taker_fee numeric(38,18) not null,
  ledger_transaction_id uuid references ledger_transactions(id),
  created_at timestamptz not null default now()
);

create index if not exists clob_trades_market_idx on clob_trades(market, created_at desc);

create table if not exists sanctions_entities (
  id uuid primary key default gen_random_uuid(),
  entity_type text not null,
  value text not null unique,
  source text not null,
  severity text not null default 'HIGH',
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists wallet_clusters (
  id uuid primary key default gen_random_uuid(),
  cluster_id text not null,
  address text not null unique,
  chain text not null,
  risk_score integer not null default 0,
  labels text[] not null default '{}',
  updated_at timestamptz not null default now()
);

create table if not exists compliance_cases (
  id uuid primary key default gen_random_uuid(),
  user_id text,
  case_type text not null,
  severity text not null,
  score integer not null,
  state text not null default 'OPEN',
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists sar_reports (
  id uuid primary key default gen_random_uuid(),
  case_id uuid references compliance_cases(id),
  user_id text,
  report jsonb not null,
  status text not null default 'DRAFT',
  generated_at timestamptz not null default now()
);

create table if not exists treasury_positions (
  id uuid primary key default gen_random_uuid(),
  asset text not null unique,
  total_assets numeric(38,18) not null default 0,
  hot_wallet_target numeric(38,18) not null default 0,
  cold_wallet_target numeric(38,18) not null default 0,
  max_exposure numeric(38,18) not null default 0,
  insurance_fund_balance numeric(38,18) not null default 0,
  updated_at timestamptz not null default now()
);

create table if not exists rebalancing_actions (
  id uuid primary key default gen_random_uuid(),
  asset text not null,
  action_type text not null,
  amount numeric(38,18) not null,
  from_tier wallet_tier,
  to_tier wallet_tier,
  state text not null default 'PLANNED',
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists oracle_source_prices (
  id uuid primary key default gen_random_uuid(),
  base_asset text not null,
  quote_asset text not null,
  source text not null,
  price numeric(38,18) not null,
  weight integer not null default 1,
  observed_at timestamptz not null default now()
);

create index if not exists oracle_source_prices_pair_idx on oracle_source_prices(base_asset, quote_asset, observed_at desc);

create table if not exists market_circuit_breakers (
  market text primary key,
  state text not null default 'OPEN',
  reason text,
  volatility_bps integer not null default 0,
  last_reference_price numeric(38,18),
  updated_at timestamptz not null default now()
);

create table if not exists recovery_checkpoints (
  id uuid primary key default gen_random_uuid(),
  checkpoint_type text not null,
  stream_id text,
  ledger_transaction_id uuid,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

insert into clob_markets(market, base_asset, quote_asset, tick_size, lot_size, min_notional, maker_fee_bps, taker_fee_bps)
values ('NENO-USDC', 'NENO', 'USDC', 0.0001, 0.0001, 1, 10, 20)
on conflict (market) do nothing;
