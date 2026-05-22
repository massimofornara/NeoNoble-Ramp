#!/usr/bin/env sh
set -eu

if [ -z "${DATABASE_URL:-}" ]; then
  echo "DATABASE_URL is required" >&2
  exit 1
fi

psql "$DATABASE_URL" -f db/migrations/20260521_transak_enterprise.sql
psql "$DATABASE_URL" -f db/migrations/20260521_exchange_core.sql
psql "$DATABASE_URL" -f db/migrations/20260522_tier1_exchange.sql
