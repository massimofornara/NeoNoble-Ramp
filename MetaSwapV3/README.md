# MetaSwap V3 Fintech Core

Self-hosted production-grade starter for a regulated hybrid exchange: token factory, controlled listing, RFQ/order-book trading, fiat-based pricing, internal liquidity balance sheet, double-entry ledger, custody policies, fiat adapters, KYC/AML/Travel Rule and market-abuse controls.

This repository is intentionally dependency-free so it can run immediately in restricted environments.

## Run

```powershell
node src/server.js
```

Default URL: `http://127.0.0.1:8080`

Wallet UI: `http://127.0.0.1:8080/wallet`

Supported wallet path:
- EIP-1193 injected wallets such as MetaMask, Trust Wallet browser provider and hardware wallets routed through those providers.
- WalletConnect-compatible clients can use the same `/wallets/challenge` and `/wallets/verify` challenge flow.
- Portfolio refresh uses live RPC calls for Ethereum, BNB Chain, Polygon, Base and Solana.

## Test

```powershell
node --test
```

## Smoke Test HTTP

```powershell
powershell -ExecutionPolicy Bypass -File scripts/smoke-http.ps1
powershell -ExecutionPolicy Bypass -File scripts/security-baseline.ps1
powershell -ExecutionPolicy Bypass -File scripts/load-test.ps1 -Requests 1000 -Concurrency 25
powershell -ExecutionPolicy Bypass -File scripts/production-readiness.ps1
```

## Key API Calls

```powershell
# Health
Invoke-RestMethod http://127.0.0.1:8080/health

# List assets
Invoke-RestMethod http://127.0.0.1:8080/assets

# Deposit fiat to primary EU user
Invoke-RestMethod http://127.0.0.1:8080/fiat/deposit -Method Post -ContentType application/json -Body '{"userId":"user-eu-1","asset":"EUR","amount":10000}'

# Create a controlled token
Invoke-RestMethod http://127.0.0.1:8080/tokens -Method Post -ContentType application/json -Body '{"issuerId":"issuer-1","symbol":"NBL","name":"Neo Noble","maxSupply":100000000,"issuePriceUsd":0.25,"chains":["ethereum","solana"],"contracts":{"ethereum":"0x1111111111111111111111111111111111111111","solana":"NBL11111111111111111111111111111111111111111"},"micaClassification":"utility"}'

# Buy token through RFQ/internal liquidity
Invoke-RestMethod http://127.0.0.1:8080/orders -Method Post -ContentType application/json -Body '{"userId":"user-eu-1","symbol":"NBL","quoteAsset":"EUR","side":"buy","amount":1000}'

# Sell token to fiat
Invoke-RestMethod http://127.0.0.1:8080/orders -Method Post -ContentType application/json -Body '{"userId":"user-eu-1","symbol":"NBL","quoteAsset":"EUR","side":"sell","amount":100}'

# Payout
Invoke-RestMethod http://127.0.0.1:8080/fiat/payout -Method Post -ContentType application/json -Body '{"userId":"user-eu-1","asset":"EUR","amount":100,"rail":"SEPA","destination":{"iban":"DE89370400440532013000","name":"Demo User"}}'
```

## Architecture

See [docs/architecture.md](docs/architecture.md).
See [docs/enterprise-operations.md](docs/enterprise-operations.md) for active-active, failover, replay, reconciliation and control-plane procedures.

## Production Configuration

Use `.env.production.example` as the required variable contract. In production, set `METASWAP_ENV=production` and `REQUIRE_LIVE_ADAPTERS=true`; regulated final-rail connectors fail closed while internal pricing, risk, treasury, surveillance and market making remain self-hosted.

## Deploy

```powershell
docker compose -f docker-compose.production.yml --env-file .env.production up -d --build
kubectl apply -f k8s/
helm upgrade --install metaswap-v3 helm/metaswap-v3
```

## Live Activation

```powershell
powershell -ExecutionPolicy Bypass -File scripts/generate-live-env.ps1 -OutputPath .env.production
# Fill regulated rail credentials and token factory addresses in .env.production.
powershell -ExecutionPolicy Bypass -File scripts/live-activation.ps1 -EnvFile .env.production
```

See [docs/live-activation.md](docs/live-activation.md).
See [docs/production-contract.md](docs/production-contract.md) for the mandatory live credential and endpoint contract.
See [docs/token-factory-deployment.md](docs/token-factory-deployment.md) for mainnet token factory deployment.

## Proofs And Recovery

```powershell
Invoke-RestMethod http://127.0.0.1:8080/proof/reserves-liabilities
powershell -ExecutionPolicy Bypass -File scripts/backup.ps1
powershell -ExecutionPolicy Bypass -File scripts/restore.ps1 -BackupPath .backups/metaswap.sqlite
```
