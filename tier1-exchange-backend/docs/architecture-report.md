# Tier-1 Exchange Core Production Upgrade Report

## Core Guarantees Preserved

- Transaction lifecycle remains event sourced:
  `ORDER_CREATED -> EXECUTION_REQUESTED -> EXECUTION_COMPLETED -> SETTLEMENT_INITIATED -> SETTLEMENT_CONFIRMED -> LEDGER_RECONCILED`.
- Ledger remains append-only and double-entry.
- Balances are reconstructed from `ledger.append` events.
- No transaction state table is mutated directly.
- Reconciliation is the final source of integrity truth.

## Distributed Cluster

- Local file-log cluster models a deployable multi-node event stream.
- Default topology: `node-0` leader plus `node-1`, `node-2`, `node-3` followers.
- Cluster state is persisted in `data/cluster-state.json`.
- Leader election promotes the healthiest active node with the longest log.
- Recovery syncs missing events from the active leader.
- Partitions are reassigned round-robin across active nodes.
- Quorum is enforced before new event appends.

## Settlement Finality

Settlement uses pluggable adapters:

- `bsc`: BSC JSON-RPC adapter for treasury-signed transaction broadcast and receipt verification.
- `ethereum`: Ethereum JSON-RPC adapter for treasury-signed transaction broadcast and receipt verification.
- `BLOCKCHAIN_EXECUTION_MODE=real` requires `SETTLEMENT_ADAPTER=bsc` or `SETTLEMENT_ADAPTER=ethereum`.
- Placeholder settlement and generated tx hashes have been removed from the execution path.
- Real broadcast requires isolated treasury signing with `TREASURY_PRIVATE_KEY`.
- ERC20 swaps build an approval pre-transaction by default, then the router swap transaction; both are treasury-signed and receipt-verified before finality.
- The treasury signer validates `TREASURY_PRIVATE_KEY` against `TREASURY_ADDRESS`, estimates gas, allocates durable pending nonces, signs locally, and broadcasts.

A transaction can become `settlement_confirmed` only when:

- tx hash matches the initiated settlement.
- receipt proof is valid.
- observed confirmations meet configured depth.
- immutable settlement proof is appended.
- ledger hash chain remains valid.
- reconciliation integrity passes.

## Valuation

The NENO valuation model is deterministic and replayable:

- `1 NENO = 20000 USDT`
- `100 NENO = 2000000 USDT`
- WBNB conversion uses `WBNB_USDT_PRICE`, default `1000`.
- Local deterministic swap result for `100 NENO -> WBNB`: `2000 WBNB`.
- Production mode can require CoinGecko or DEX Screener via `PRICE_DISCOVERY_MODE=real`.
- External price snapshots are persisted with `source`, `capturedAt`, and `replayKey`.

Valuation metadata is persisted in:

- `orders.created`
- `execution.requested`
- `execution.completed`
- `settlement.initiated`
- `ledger.append`
- audit reports

## Observability

- Prometheus metrics exposed at `/metrics`.
- Structured JSON logs include component, event, correlation, and trace-compatible IDs.
- Trace spans are emitted as structured logs.
- Grafana dashboard seed is stored at `deploy/observability/grafana-dashboard.json`.

Metrics include:

- event throughput
- execution latency
- settlement latency
- replay duration
- reconciliation integrity failures
- DLQ events

## Disaster Recovery

- Ledger snapshots are created through `POST /snapshots/ledger`.
- Recovery verification is exposed at `GET /recovery/verify`.
- Backup export is exposed at `POST /backup/export`.
- Compaction is snapshot-indexed and non-destructive by default.

## PostgreSQL Persistence

- `PERSISTENCE_DRIVER=postgres` enables PostgreSQL write-through for exchange events, ledger entries, and settlement proofs.
- `DATABASE_URL` is required in PostgreSQL mode.
- Migration: `db/migrations/001_append_only_exchange.sql`.
- Append-only enforcement is implemented with PostgreSQL triggers rejecting update/delete operations.
- WAL replication is expected at the database layer.

## Security

- Mutation endpoints require idempotency keys.
- Webhooks require HMAC signature plus timestamp and nonce replay protection.
- JWT signing keys can be rotated.
- Audit reports are HMAC signed.
- API rate limiting is enforced per remote/path identity.

## Deployment

- Dockerfile included.
- Kubernetes manifests included under `deploy/kubernetes`.
- Helm chart included under `deploy/helm/tier1-exchange`.
- Event stream nodes are modeled as a StatefulSet.
- PostgreSQL is modeled as a StatefulSet with persistent volume.
- Settlement, reconciliation, and risk workers are modeled as independent deployments.
- API layer has rolling deployment and HPA.
- ConfigMaps, Secrets, readiness probes, and liveness probes are included.

## Production Gate

`GET /production/preflight?flow=swap` must pass before a real production swap can execute. `flow=offramp` validates off-ramp custody settlement, and the default preflight validates both paths.

Required runtime values:

- `BLOCKCHAIN_EXECUTION_MODE=real`
- `SETTLEMENT_ADAPTER=bsc` or `SETTLEMENT_ADAPTER=ethereum`
- `BSC_RPC_URL` or `ETHEREUM_RPC_URL`
- `TREASURY_ADDRESS`
- `TREASURY_PRIVATE_KEY`
- `BSC_SWAP_ROUTER_ADDRESS`
- `NENO_CONTRACT_ADDRESS`
- `WBNB_CONTRACT_ADDRESS`
- `OFFRAMP_CUSTODY_ADDRESS`
- `PERSISTENCE_DRIVER=postgres`
- `DATABASE_URL`

## Validation Summary

Validated locally on `http://127.0.0.1:4100`:

- `npm run build`: passed.
- `npm run demo`: passed.
- Swap `100 NENO -> WBNB`: `settlement_confirmed`, `LEDGER_RECONCILED`, integrity true.
- Offramp `200 NENO -> 4000000 USDT`: `settlement_confirmed`, `LEDGER_RECONCILED`, integrity true.
- Settlement proof hash chains: valid.
- Ledger hash chain: valid.
- Recovery verification from snapshot: valid.
- Leader failover and node recovery: verified.
- DLQ: empty.

Latest production validation uses Neon PostgreSQL as the production source of truth and blocks real settlement before broadcast when chain liquidity, custody, or quote invariants cannot be satisfied. No generated tx hash is produced.
