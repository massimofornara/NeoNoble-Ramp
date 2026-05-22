# Operations Runbook

## Environments

- local: SQLite persistence, internal execution, optional external connector submission.
- staging: live connector endpoints with partner sandbox credentials, `REQUIRE_LIVE_ADAPTERS=true`.
- production: live connector endpoints, secrets from Vault/Kubernetes secrets, WAF and private networking enabled.

## Deploy

```powershell
Copy-Item .env.example .env.production
docker compose -f docker-compose.production.yml up -d --build
```

## Health

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
Invoke-RestMethod http://127.0.0.1:8080/events?limit=20
```

## Backup

Stop writes, snapshot `.data/metaswap.sqlite`, PostgreSQL, Redpanda, and ClickHouse volumes. Store encrypted copies in two regions.

## Restore

Restore ledger database first, then event log, then market data. Run `node --test`, start one API replica, verify `/health`, then scale replicas.

## Incident Actions

- Trading incident: disable ingress to `/orders`, preserve `/ledger/balances`.
- Custody incident: block `/custody/withdraw`, rotate custody credentials.
- Fiat incident: block `/fiat/payout`, keep deposit webhooks in outbox.
- Oracle incident: restrict affected assets to RFQ-only.
