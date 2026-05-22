#!/usr/bin/env sh
set -eu

BASE_URL="${BASE_URL:-http://localhost:3000}"
TOKEN="${RECONCILIATION_ADMIN_TOKEN:-}"

curl -fsS -X POST "${BASE_URL}/api/exchange/reconcile" \
  ${TOKEN:+-H "Authorization: Bearer ${TOKEN}"}

echo
echo "Run ledger imbalance SQL from README_EXCHANGE_GRADE.md after PITR restore."
