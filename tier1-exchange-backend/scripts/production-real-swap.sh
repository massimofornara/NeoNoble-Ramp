#!/usr/bin/env bash
set -euo pipefail

echo "=== 1. SET ENV (LOW COST MODE) ==="
load_env_file() {
  local file="$1"
  [ -f "$file" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    line="${line#$'\xef\xbb\xbf'}"
    [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" != *"="* ]] && continue
    local key="${line%%=*}"
    local value="${line#*=}"
    key="$(echo "$key" | xargs)"
    value="${value%\"}"
    value="${value#\"}"
    value="${value%\'}"
    value="${value#\'}"
    if [ -n "$key" ] && [ -z "${!key:-}" ]; then
      export "$key=$value"
    fi
  done < "$file"
}

load_env_file "../.env"
load_env_file ".env"
export BLOCKCHAIN_EXECUTION_MODE="${BLOCKCHAIN_EXECUTION_MODE:-real}"
export SETTLEMENT_ADAPTER="${SETTLEMENT_ADAPTER:-bsc}"
export CHAIN_ID="${CHAIN_ID:-56}"
export GAS_STRATEGY="${GAS_STRATEGY:-optimized_low}"
export MAX_GAS_PRICE="${MAX_GAS_PRICE:-1000000000}"
export PERSISTENCE_DRIVER="${PERSISTENCE_DRIVER:-postgres}"
export PRICE_DISCOVERY_MODE="${PRICE_DISCOVERY_MODE:-real}"
export PORT="${PORT:-4100}"
export NODE_OPTIONS="${NODE_OPTIONS:---use-system-ca}"

echo "=== 2. VERIFY REQUIRED ENV ==="
test -n "${BSC_RPC_URL:-}" || (echo "missing BSC_RPC_URL" && exit 1)
test -n "${TREASURY_PRIVATE_KEY:-}" || (echo "missing TREASURY_PRIVATE_KEY" && exit 1)
test -n "${TREASURY_ADDRESS:-}" || (echo "missing TREASURY_ADDRESS" && exit 1)
test -n "${DATABASE_URL:-}" || (echo "missing DATABASE_URL" && exit 1)
[[ "$DATABASE_URL" == postgresql://* || "$DATABASE_URL" == postgres://* ]] || (echo "DATABASE_URL must use postgres/postgresql scheme" && exit 1)
[[ "$DATABASE_URL" == *".neon.tech"* ]] || (echo "DATABASE_URL must use a Neon .neon.tech host" && exit 1)
[[ "$DATABASE_URL" == *"sslmode=require"* ]] || (echo "DATABASE_URL must include sslmode=require" && exit 1)
[[ "$DATABASE_URL" != *"@postgres/"* && "$DATABASE_URL" != *"@localhost"* && "$DATABASE_URL" != *"@127.0.0.1"* ]] || (echo "DATABASE_URL must not point to localhost or docker hostname postgres" && exit 1)
test -n "${BSC_SWAP_ROUTER_ADDRESS:-}" || (echo "missing BSC_SWAP_ROUTER_ADDRESS" && exit 1)
test -n "${NENO_CONTRACT_ADDRESS:-}" || (echo "missing NENO_CONTRACT_ADDRESS" && exit 1)
test -n "${WBNB_CONTRACT_ADDRESS:-}" || (echo "missing WBNB_CONTRACT_ADDRESS" && exit 1)

echo "=== 3. VERIFY BSC RPC JSON-RPC ==="
RPC_CURL_BIN="curl"
LOCAL_CURL_BIN="curl"

"$RPC_CURL_BIN" -fsS "$BSC_RPC_URL" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"eth_chainId","params":[]}' | grep -E '"result":"0x38"|0x38'

echo "=== 4. START BACKEND ==="
npm run build
RUNTIME_NODE="node"
if command -v node.exe >/dev/null 2>&1; then
  export WSLENV="PORT:BSC_RPC_URL:ETHEREUM_RPC_URL:TREASURY_ADDRESS:TREASURY_PRIVATE_KEY:DATABASE_URL:BLOCKCHAIN_EXECUTION_MODE:SETTLEMENT_ADAPTER:CHAIN_ID:BSC_CHAIN_ID:GAS_STRATEGY:MAX_GAS_PRICE:PERSISTENCE_DRIVER:PRICE_DISCOVERY_MODE:BSC_SWAP_ROUTER_ADDRESS:NENO_CONTRACT_ADDRESS:WBNB_CONTRACT_ADDRESS:OFFRAMP_CUSTODY_ADDRESS:SWAP_APPROVAL_MODE:NODE_OPTIONS${WSLENV:+:$WSLENV}"
  RUNTIME_NODE="node.exe"
  if command -v curl.exe >/dev/null 2>&1; then
    LOCAL_CURL_BIN="curl.exe"
  fi
fi
"$RUNTIME_NODE" dist/api/cli.js &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT
sleep 5

echo "=== 5. HEALTH + PRODUCTION PREFLIGHT ==="
"$LOCAL_CURL_BIN" -fsS "http://127.0.0.1:${PORT:-4100}/health"
PREFLIGHT="$("$LOCAL_CURL_BIN" -fsS "http://127.0.0.1:${PORT:-4100}/production/preflight?flow=swap")"
echo "$PREFLIGHT"
echo "$PREFLIGHT" | grep -E '"ready":[[:space:]]*true'

echo "=== 6. EXECUTE REAL SWAP (100 NENO -> WBNB) ==="
SWAP_RESPONSE="$("$LOCAL_CURL_BIN" -sS -X POST "http://127.0.0.1:${PORT:-4100}/production/execute-real-swap" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: production-real-swap-$(date +%s)" \
  -d '{
    "userId": "massi-prod-001",
    "fromToken": "NENO",
    "toToken": "WBNB",
    "amount": "100",
    "executionMode": "real",
    "gasStrategy": "low_cost"
  }')"
echo "$SWAP_RESPONSE"
if echo "$SWAP_RESPONSE" | grep -q '"error"'; then
  exit 1
fi

echo "=== DONE ==="
