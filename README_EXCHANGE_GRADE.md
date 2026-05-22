# NeoNoble Exchange-Grade Architecture

NeoNoble is now split into two bounded systems:

- Fiat Rails: Transak remains the external fiat on/off-ramp and KYC provider.
- NeoNoble Core: internal exchange engine with double-entry ledger, swaps, risk, reconciliation, event sourcing, and observability.

## Folder Architecture

```text
app/api/exchange/*              Exchange API routes
app/exchange/page.js            Exchange-grade UX shell
components/PortfolioDashboard.tsx
components/ExchangeSwapPanel.tsx
components/TransactionHistory.tsx
lib/exchange/ledger.ts          Double-entry accounting engine
lib/exchange/stateMachine.ts    CREATED -> PENDING -> PROCESSING -> SETTLED/FAILED/REVERSED
lib/exchange/eventBus.ts        Redis Streams event bus with replay
lib/exchange/riskEngine.ts      Velocity, AML, wallet, exposure rules
lib/exchange/pricingEngine.ts   Oracle + spread + slippage
lib/exchange/swapEngine.ts      Internal MARKET/LIMIT swap executor
lib/exchange/reconciliation.ts  Transak-vs-ledger reconciliation
workers/reconciliationWorker.js Async reconciliation worker
db/migrations/20260521_exchange_core.sql
deploy/observability/grafana-exchange-dashboard.json
deploy/k8s/reconciliation-worker.yaml
```

## Ledger Rules

- Every ledger transaction has an idempotency key.
- Every transaction is posted inside a PostgreSQL `SERIALIZABLE` transaction.
- Journal entries must balance per asset: total debit equals total credit.
- Balances are updated only by `postLedgerTransaction`, never directly by business APIs.
- Holds move available funds to held funds and can be released or settled.
- Immutable audit log is hash chained.

Core tables:

- `accounts`
- `balances`
- `ledger_transactions`
- `journal_entries`
- `holds`
- `settlements`
- `transaction_events`
- `immutable_audit_log`

## State Machine

Allowed transitions:

```text
CREATED -> PENDING
CREATED -> FAILED
PENDING -> PROCESSING
PENDING -> FAILED
PENDING -> REVERSED
PROCESSING -> SETTLED
PROCESSING -> FAILED
PROCESSING -> REVERSED
SETTLED -> REVERSED
```

No transition is accepted outside this graph. Every transition writes an immutable `transaction_events` row.

## Event Bus

Redis Streams stream:

```text
exchange:events
```

Events:

- `TransactionCreated`
- `FiatDepositConfirmed`
- `SwapExecuted`
- `LedgerUpdated`
- `RiskFlagTriggered`
- `SettlementReconciled`

Replay:

```bash
curl "http://localhost:3000/api/exchange/events?from=0-0&count=100"
```

## APIs

```bash
GET  /api/exchange/portfolio?userId=...
GET  /api/exchange/swap?fromAsset=NENO&toAsset=USDC&amount=1
POST /api/exchange/swap
GET  /api/exchange/transactions?userId=...
GET  /api/exchange/risk?userId=...
POST /api/exchange/reconcile
```

Swap body:

```json
{
  "userId": "user-123",
  "fromAsset": "NENO",
  "toAsset": "USDC",
  "amount": "1",
  "orderType": "MARKET",
  "maxSlippageBps": 100,
  "idempotencyKey": "client-unique-key",
  "correlationId": "trace-id"
}
```

## Risk Engine

Implemented controls:

- per-user hourly/daily swap velocity
- repeated rapid swap blocks
- blocked wallet list
- high slippage tolerance scoring
- large fiat flow scoring
- automatic risk events and event-bus publication

Environment:

```bash
RISK_MAX_HOURLY_SWAPS=20
RISK_MAX_DAILY_SWAPS=100
RISK_MAX_FIAT_SINGLE_FLOW=50000
RISK_BLOCK_SCORE=70
RISK_BLOCKED_WALLETS=0x...
```

## Reconciliation

The reconciliation worker compares Transak completed webhook records against ledger settlement rows and posts missing settlement transactions.

```bash
npm run worker:reconcile
curl -X POST http://localhost:3000/api/exchange/reconcile \
  -H "Authorization: Bearer $RECONCILIATION_ADMIN_TOKEN"
```

## Observability

- Prometheus: `/api/metrics`
- Grafana dashboard: `deploy/observability/grafana-exchange-dashboard.json`
- OpenTelemetry: `instrumentation.ts`
- Correlation IDs: carried through ledger, events, swaps, reconciliation

Metrics:

- `exchange_swaps_total`
- `exchange_settlement_latency_seconds`
- `exchange_liquidity_depth`
- `exchange_risk_events_total`
- Transak conversion/session metrics from the fiat gateway layer

## Scaling

- API services are stateless and horizontally scaled by Kubernetes HPA.
- Writes use `DATABASE_URL`; read-heavy endpoints use `DATABASE_REPLICA_URL` when configured.
- Redis provides rate-limit counters, event-stream replay, and webhook anti-replay.
- Reconciliation is queue/worker based and can scale independently from the API deployment.
- Swap execution uses PostgreSQL `SERIALIZABLE` atomic commits to preserve ledger finality under concurrent load.

## Security

- Transak webhook IP allowlist via `TRANSAK_WEBHOOK_IP_ALLOWLIST`
- Transak signed webhook JWT verification
- Optional HMAC verification if Transak signature header is present
- Redis replay protection for webhook event IDs
- strict CSP and iframe allowlist
- user/IP rate limiting
- encrypted PII table with key versioning
- immutable append-only audit log
- secret rotation through env/key version fields

## Production Commands

```bash
npm install
npm run typecheck
npm run build
./scripts/migrate.sh
npm run migrate:tier1
docker build -t neonoble-ramp:exchange .
docker compose up --build
kubectl apply -f deploy/k8s/
helm upgrade --install neonoble-ramp ./deploy/helm/neonoble-ramp --namespace neonoble-ramp --create-namespace
```

API reference: [docs/API_EXCHANGE.md](./docs/API_EXCHANGE.md)

Incident response: [docs/INCIDENT_RESPONSE_RUNBOOK.md](./docs/INCIDENT_RESPONSE_RUNBOOK.md)

## Disaster Recovery

RPO target: 5 minutes. RTO target: 30 minutes.

1. PostgreSQL point-in-time recovery from WAL archive.
2. Redis Streams replay from persisted AOF or Kafka replacement topic.
3. Rebuild balances by replaying `journal_entries` grouped by account and asset.
4. Reconcile all external Transak completed orders against `ledger_transactions.external_provider='transak'`.
5. Verify hash chain continuity in `immutable_audit_log`.
6. Freeze withdrawals if any ledger imbalance query returns rows.

Ledger imbalance check:

```sql
select ledger_transaction_id, asset,
       sum(case when direction = 'DEBIT' then amount else -amount end) as imbalance
from journal_entries
group by ledger_transaction_id, asset
having sum(case when direction = 'DEBIT' then amount else -amount end) <> 0;
```
