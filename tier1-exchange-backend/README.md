# Tier-1 Exchange Backend

Production-ready exchange backend foundation with:

- Event-driven architecture through a Kafka/Redpanda-compatible `EventBus` abstraction.
- Persistent append-only event stream in `data/event-stream.jsonl`.
- Consumer groups with committed offsets in `data/consumer-offsets.json`.
- At-least-once delivery, retry-safe consumers, and DLQ in `data/dead-letter.jsonl`.
- Append-only cryptographic ledger with `previousHash` / `currentHash`.
- Balances computed by aggregation, never mutation.
- Idempotency enforcement on every mutation endpoint.
- Strict service separation: Order, Wallet, Compliance, Execution, Settlement, Ledger, Reconciliation.
- Retry-safe consumers and dead-letter queue.
- Replayable transaction state from events.
- Audit/reporting layer and optional deterministic matching engine.
- Local multi-node replicated event log with leader plus three replicas.
- Leader election, automatic failover, partition reassignment, and node recovery in the file-log cluster.
- Exactly-once processing layer via endpoint idempotency, durable processed-event dedup, and consumer offsets.
- Expanded risk layer with dynamic exposure limits, account risk scoring, abnormal execution detection, velocity windows, and circuit breaker state.
- Pluggable settlement adapters for BSC JSON-RPC and Ethereum JSON-RPC.
- Production-real settlement mode with no placeholder fallback.
- Treasury signer abstraction for isolated EVM hot-wallet signing and RPC broadcasting.
- Immutable append-only settlement proof store with hash chaining.
- Optional PostgreSQL append-only primary persistence with anti-update/delete triggers.
- CoinGecko / DEX Screener price discovery with replay-safe oracle snapshots.
- Prometheus metrics, Grafana dashboard JSON, structured logs, and trace-compatible correlation IDs.
- Snapshot, backup, recovery verification, and snapshot-indexed compaction tooling.
- Kubernetes manifests and Helm chart for HA deployment patterns.

## Run

```bash
npm run build
npm run demo
npm run start
```

The HTTP server listens on `PORT` or `4100`.

By default, persistent data is stored in `./data`. Override with:

```bash
set TIER1_DATA_DIR=C:\path\to\data
```

## Endpoints

Mutation endpoints require an `Idempotency-Key` header or `idempotencyKey` body field.

- `POST /orders`
- `POST /swap`
- `POST /offramp`
- `POST /execution`
- `POST /ledger/append`
- `POST /webhooks/provider`
- `GET /fireblocks/readiness`
- `GET /fireblocks/vault`
- `POST /fireblocks/transactions`
- `POST /offramp/fireblocks`
- `POST /webhooks/fireblocks`
- `GET /offramp/status/:orderId`
- `GET /ledger/balance/:accountId`
- `GET /reconciliation/:transactionId`
- `GET /events/:transactionId`
- `GET /replay/:transactionId`
- `GET /audit/:transactionId`
- `GET /dead-letter`
- `GET /metrics`
- `GET /cluster`
- `POST /cluster/failover`
- `POST /cluster/recover`
- `POST /cluster/reassign-partitions`
- `POST /snapshots/ledger`
- `GET /recovery/verify`
- `POST /backup/export`
- `GET /compaction/plan`
- `GET /risk/:userId`
- `GET /security/status`
- `POST /security/jwt/rotate`
- `GET /production/preflight`
- `GET /assets/registry`
- `GET /treasury/status`
- `GET /treasury/exposure`
- `GET /treasury/rebalance-report`
- `POST /production/execute-real-swap`
- `POST /matching/orders`
- `POST /matching/cancel`
- `GET /matching/book/:symbol`

## Event Envelope

Every event is persisted as:

```json
{
  "eventId": "uuid",
  "type": "orders.created",
  "transactionId": "uuid",
  "timestamp": "ISO-8601",
  "payload": {}
}
```

## State Machine

```text
ORDER_CREATED
-> EXECUTION_REQUESTED
-> EXECUTION_COMPLETED
-> SETTLEMENT_INITIATED
-> SETTLEMENT_CONFIRMED
-> LEDGER_RECONCILED
```

No transaction state table is mutated. State is rebuilt from the event log.

## Distributed Cluster

The local event stream is now modeled as a deployable multi-node topology:

- `node-0` leader plus three follower nodes by default.
- Quorum enforcement before appends.
- Deterministic leader election when the leader is marked offline.
- Partition assignment across active nodes.
- Node recovery by replaying the leader log into the recovered node.
- Restart consistency by loading `data/cluster-state.json` and syncing replicas from the leader.

Local control endpoints:

```bash
curl http://127.0.0.1:4100/cluster
curl -X POST http://127.0.0.1:4100/cluster/failover -H "Idempotency-Key: fail-node-0" -d "{\"nodeId\":\"node-0\"}"
curl -X POST http://127.0.0.1:4100/cluster/recover -H "Idempotency-Key: recover-node-0" -d "{\"nodeId\":\"node-0\"}"
```

## Production Notes

The current `KafkaCompatibleEventStream` uses a durable JSONL file log so the project runs locally without external infrastructure. It preserves Kafka/Redpanda concepts: topic, key, partition, offset, consumer group, committed offsets, at-least-once delivery, DLQ, and replay.

To move to Redpanda/Kafka, replace only `src/core/eventBus.ts`; services depend on the `EventBus` interface, not on the file-log implementation.

## Settlement Proofs

Settlement is proof-based:

- `settlement.initiated` is emitted only after the settlement adapter broadcasts a treasury-signed transaction.
- Local placeholder settlement has been removed; unsupported settlement configuration fails explicitly.
- `bsc` and `ethereum` use treasury signing, JSON-RPC broadcasting, receipt verification, and confirmation-depth validation when `BSC_RPC_URL` or `ETHEREUM_RPC_URL` are configured.
- Confirmation depth is configurable per adapter.
- `POST /webhooks/provider` requires HMAC signature, timestamp, and replay nonce.
- `settlement.confirmed` must match initiated tx hash and settlement id.
- Reconciliation validates event replay, ledger hash chain, receipt depth, and immutable settlement proof hash chain.

To use real chain verification and broadcasting:

```bash
set BLOCKCHAIN_EXECUTION_MODE=real
set SETTLEMENT_ADAPTER=bsc
set BSC_RPC_URL=https://your-bsc-rpc
set BSC_CONFIRMATION_DEPTH=15
set TREASURY_ADDRESS=0x...
set TREASURY_PRIVATE_KEY=...
set BSC_SWAP_ROUTER_ADDRESS=0x...
set NENO_CONTRACT_ADDRESS=0x...
set USDT_CONTRACT_ADDRESS=0x...
set USDC_CONTRACT_ADDRESS=0x...
set WBNB_CONTRACT_ADDRESS=0x...
set ETH_CONTRACT_ADDRESS=0x...
set BTC_CONTRACT_ADDRESS=0x...
set OFFRAMP_CUSTODY_ADDRESS=0x...
set SWAP_APPROVAL_MODE=exact
```

If `BLOCKCHAIN_EXECUTION_MODE=real` is set, placeholder settlement and environment-based settlement fallbacks are disabled. Production execution must build calldata through the swap/offramp routers, sign through `TreasurySigner`, broadcast through the configured RPC, and verify the receipt before finality. ERC20 swaps default to an exact approval transaction followed by the router swap; set `SWAP_APPROVAL_MODE=preapproved` only when treasury allowances are already managed externally.

Production boot also validates the EVM asset registry for `NENO`, `USDT`, `USDC`, `WBNB`, `ETH`, and `BTC`, including checksum-compatible addresses, decimals, chain metadata, venue compatibility, RFQ eligibility, and bridge compatibility.

The treasury signer uses `TREASURY_PRIVATE_KEY` only inside the signing path, validates that it matches `TREASURY_ADDRESS`, estimates gas, allocates a pending nonce, signs locally, then broadcasts with retry.

`GET /production/preflight?flow=swap` must be green before `POST /production/execute-real-swap` is allowed. `GET /production/preflight?flow=offramp` validates the custody-transfer path, while the default preflight validates both flows.

## Fireblocks Crypto-Native Rail

Fireblocks is integrated as a custody, vault transfer, treasury, and crypto-native settlement rail. It does not simulate fiat payouts and it never marks `settlement_confirmed` or `payout_confirmed` from local state alone.

Configuration:

```bash
set FIREBLOCKS_API_KEY=your_api_key
set FIREBLOCKS_PRIVATE_KEY_PATH=C:\secure\fireblocks-api-key.pem
set FIREBLOCKS_BASE_URL=https://sandbox-api.fireblocks.io
set FIREBLOCKS_VAULT_ACCOUNT_ID=0
set FIREBLOCKS_WEBHOOK_SECRET=optional_internal_relay_secret
set FIREBLOCKS_WEBHOOK_JWKS_URL=https://sandbox-keys.fireblocks.io/.well-known/jwks.json
set FIREBLOCKS_NENO_ASSET_ID=NENO_BSC
set FIREBLOCKS_STABLECOIN_ASSET_ID=USDC
set FIREBLOCKS_CONFIRMATION_THRESHOLD=15
set FIREBLOCKS_PAYMENT_ACCOUNT_ID=your_fireblocks_fiat_or_exchange_account
set FIREBLOCKS_PAYMENT_ACCOUNT_TYPE=FIAT_ACCOUNT
set FIREBLOCKS_MASSIMO_FORNARA_PAYEE_ACCOUNT_ID=preconfigured_payee_account_id
set FIREBLOCKS_MASSIMO_FORNARA_PAYEE_ACCOUNT_TYPE=FIAT_ACCOUNT
set FIREBLOCKS_PAYOUT_ASSET_ID=EUR
```

JWT requests are signed at runtime from `FIREBLOCKS_PRIVATE_KEY_PATH`; the private key and API key are never logged. `POST /v1/transactions` uses `externalTxId` for idempotent provider correlation.

Readiness and vault balance checks:

```bash
curl http://127.0.0.1:4100/fireblocks/readiness
curl http://127.0.0.1:4100/fireblocks/vault
```

Create a crypto-native Fireblocks transfer:

```bash
curl -X POST http://127.0.0.1:4100/fireblocks/transactions ^
  -H "Content-Type: application/json" ^
  -H "Idempotency-Key: fb-transfer-0001" ^
  -d "{\"accountId\":\"massi-prod-001\",\"assetId\":\"NENO_BSC\",\"amount\":\"100\",\"destinationWallet\":\"0x0000000000000000000000000000000000000000\",\"purpose\":\"offramp\",\"executionMode\":\"real\"}"
```

Create an offramp settlement transfer through Fireblocks custody:

```bash
curl -X POST http://127.0.0.1:4100/offramp/fireblocks ^
  -H "Content-Type: application/json" ^
  -H "Idempotency-Key: fb-offramp-0001" ^
  -d "{\"userId\":\"massi-prod-001\",\"fromToken\":\"NENO\",\"assetId\":\"NENO_BSC\",\"amount\":\"100\",\"destinationWallet\":\"0x0000000000000000000000000000000000000000\",\"executionMode\":\"real\",\"allowDirectCustomTokenTransfer\":true}"
```

Webhook processing:

```bash
curl -X POST http://127.0.0.1:4100/webhooks/fireblocks \
  -H "Content-Type: application/json" \
  -H "Fireblocks-Webhook-Signature: <detached-jws-from-fireblocks>" \
  --data-binary @fireblocks-webhook.json
```

The webhook handler verifies Fireblocks v2 detached JWS/JWKS signatures when available. A shared-secret HMAC mode is supported only for an internal relay that cannot forward the JWS header.

Finality rules:

1. A Fireblocks transaction must be known from a local `fireblocks.transaction.created` event.
2. Fireblocks status must reach `COMPLETED`.
3. The provider payload must contain a valid tx hash, matching asset, matching amount, matching destination wallet, and enough confirmations.
4. Only then the service emits `settlement.initiated`, `settlement.pending_confirmation`, and `settlement.confirmed`.
5. `payout.confirmed` is emitted only after reconciliation returns `status=settlement_confirmed` and `integrity=true`.

Status:

```bash
curl http://127.0.0.1:4100/offramp/status/<order_id>
```

Sandbox smoke check:

```bash
npm run build
npm run fireblocks:sandbox-check
```

Execute Fireblocks Payments payouts for already confirmed offramp settlements:

```bash
npm run build
npm run fireblocks:payout-offramps
```

This command requires Fireblocks Payments Engine to be enabled and requires preconfigured Fireblocks `paymentAccount` and Massimo Fornara `payeeAccount` IDs. The raw IBAN is retained in the audit destination metadata, but Fireblocks payout execution uses Fireblocks account IDs as required by the Payments Payout API. It emits `payout.confirmed` only when Fireblocks returns `state=FINALIZED` and `status=DONE`.

If 0x, 1inch, DEX RFQ, or OTC liquidity cannot produce a real executable route before Fireblocks custody transfer, `/offramp/fireblocks` fails with `INSUFFICIENT_REAL_LIQUIDITY`; it does not create synthetic conversion or payout finality.

## Ledger Integrity

Each ledger entry includes:

```json
{
  "eventId": "uuid",
  "transactionId": "uuid",
  "accountId": "acct_user_001",
  "delta": "240000",
  "asset": "USDT",
  "timestamp": "ISO-8601",
  "previousHash": "sha256",
  "currentHash": "sha256"
}
```

Entries are append-only. There are no update or delete operations.

## Live Flow Endpoints

`POST /swap`

```json
{
  "userId": "massi-prod-001",
  "fromToken": "NENO",
  "toToken": "WBNB",
  "amount": "100",
  "executionMode": "real"
}
```

The swap flow applies deterministic valuation before execution:

```text
1 NENO = 20000 USDT
100 NENO = 2000000 USDT
WBNB amount = sourceValuationUSDT / WBNB_USDT_PRICE
```

`WBNB_USDT_PRICE` defaults to `1000`, so the local deterministic result for `100 NENO` is `2000 WBNB`.

Set `PRICE_DISCOVERY_MODE=real` to require CoinGecko or DEX Screener pricing. The selected price is persisted as an oracle snapshot in events, settlement metadata, ledger entries, and audit reports.

## PostgreSQL

Set:

```bash
set PERSISTENCE_DRIVER=postgres
set DATABASE_URL=postgres://user:pass@host:5432/db
```

The schema is available at `db/migrations/001_append_only_exchange.sql`. Runtime startup also creates append-only tables if PostgreSQL is enabled.

`POST /offramp`

```json
{
  "userId": "massi-prod-001",
  "fromToken": "NENO",
  "amount": "200",
  "fiatCurrency": "USDT",
  "rate": "20000",
  "executionMode": "real"
}
```

Both endpoints still require `Idempotency-Key`.

## Continuous Production Execution

`npm run stress:intent` runs the production ladder directly through the intent layer without extra test-mode gates:

- Swaps: `50`, `100`, `500`, `1000`, `5000`, `10000`, `20000`, `50000`, `100000`, and `200000` NENO into `USDT`, `USDC`, `WBNB`, `ETH`, and `BTC`.
- Offramp: `100`, `500`, `1000`, `5000`, `10000`, and `20000` NENO into `EUR`.

The runner still requires production preflight to pass. It fails explicitly when RPC, treasury, Postgres, chain config, custody, or price configuration is missing, and it never substitutes mock settlement or synthetic transaction hashes.

`GET /orders/:transactionId` reports `settlement_confirmed` only after:

1. Order event has been appended.
2. Execution has completed asynchronously.
3. Settlement has initiated with a tx hash.
4. Internal/provider finality confirmation has been appended.
5. Ledger has appended double-entry entries.
6. Reconciliation proves event replay, settlement proof, and ledger integrity.

## Disaster Recovery

```bash
curl -X POST http://127.0.0.1:4100/snapshots/ledger -H "Idempotency-Key: snapshot-1" -d "{}"
curl http://127.0.0.1:4100/recovery/verify
curl -X POST http://127.0.0.1:4100/backup/export -H "Idempotency-Key: backup-1" -d "{}"
curl http://127.0.0.1:4100/compaction/plan
```

Set `SNAPSHOT_INTERVAL_MS` to enable periodic snapshots.

## Deployment

- Raw Kubernetes manifests: `deploy/kubernetes`
- Helm chart: `deploy/helm/tier1-exchange`
- Grafana dashboard: `deploy/observability/grafana-dashboard.json`

Example:

```bash
helm install tier1 ./deploy/helm/tier1-exchange
```
