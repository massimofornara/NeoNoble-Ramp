create extension if not exists "pgcrypto";

create table if not exists transactions (
  id uuid primary key default gen_random_uuid(),
  provider text not null default 'transak',
  transak_order_id text,
  partner_order_id text not null,
  partner_customer_id text,
  product text not null,
  status text not null,
  fiat_currency text,
  crypto_currency text,
  network text,
  wallet_address text,
  fiat_amount numeric(24, 8),
  crypto_amount numeric(36, 18),
  fee_fiat numeric(24, 8),
  widget_url text,
  request_payload jsonb,
  response_payload jsonb,
  ip_hash text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint transactions_partner_order_unique unique (partner_order_id)
);

create index if not exists transactions_provider_status_idx on transactions(provider, status);
create index if not exists transactions_transak_order_id_idx on transactions(transak_order_id);
create index if not exists transactions_partner_customer_id_idx on transactions(partner_customer_id);
create index if not exists transactions_created_at_idx on transactions(created_at desc);

create table if not exists kyc_sessions (
  id uuid primary key default gen_random_uuid(),
  provider text not null default 'transak',
  partner_user_id text,
  partner_customer_id text,
  kyc_status text not null,
  event_id text,
  raw_payload jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint kyc_sessions_provider_event_unique unique(provider, event_id)
);

create index if not exists kyc_sessions_partner_customer_idx on kyc_sessions(partner_customer_id);
create index if not exists kyc_sessions_status_idx on kyc_sessions(kyc_status);

create table if not exists webhook_events (
  id uuid primary key default gen_random_uuid(),
  provider text not null,
  event_id text not null,
  event_name text not null,
  raw_payload jsonb not null,
  decoded_payload jsonb,
  replay_detected boolean not null default false,
  processed boolean not null default false,
  error_message text,
  processed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint webhook_events_provider_event_unique unique(provider, event_id)
);

create index if not exists webhook_events_provider_name_idx on webhook_events(provider, event_name);
create index if not exists webhook_events_processed_idx on webhook_events(processed);
create index if not exists webhook_events_created_at_idx on webhook_events(created_at desc);

create table if not exists swap_events (
  id uuid primary key default gen_random_uuid(),
  source_asset text not null default 'NENO',
  destination_asset text not null,
  source_network text not null,
  destination_network text,
  wallet_address text,
  amount_in numeric(36, 18),
  amount_out numeric(36, 18),
  status text not null,
  provider text not null default 'neonoble',
  route_payload jsonb,
  tx_hash text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists swap_events_status_idx on swap_events(status);
create index if not exists swap_events_wallet_idx on swap_events(wallet_address);

create table if not exists user_wallets (
  id uuid primary key default gen_random_uuid(),
  user_id text,
  partner_customer_id text,
  wallet_address text not null,
  chain_id text not null,
  network text not null,
  is_primary boolean not null default false,
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint user_wallets_wallet_chain_unique unique(wallet_address, chain_id)
);

create index if not exists user_wallets_partner_customer_idx on user_wallets(partner_customer_id);

create table if not exists revenue_tracking (
  id uuid primary key default gen_random_uuid(),
  provider text not null default 'transak',
  partner_order_id text not null,
  transak_order_id text,
  revenue_account_id text,
  fiat_currency text,
  fiat_amount numeric(24, 8),
  partner_fee_in_usd numeric(24, 8),
  partner_fee_decimal numeric(10, 8),
  fee_payload jsonb,
  booked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint revenue_tracking_partner_order_unique unique(provider, partner_order_id)
);

create index if not exists revenue_tracking_booked_at_idx on revenue_tracking(booked_at desc);
