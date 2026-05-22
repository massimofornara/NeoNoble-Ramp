# Exchange Incident Response Runbook

## Severity 0: Ledger Imbalance

1. Freeze withdrawals by disabling `/api/withdraw` at ingress or setting withdrawal feature flag off.
2. Run the imbalance query from `README_EXCHANGE_GRADE.md`.
3. Stop trading canary and main trading routes.
4. Snapshot PostgreSQL and Redis AOF.
5. Run `node tools/recovery/rebuild-ledger.js`.
6. Reconcile Transak completed orders against ledger external IDs.
7. Re-enable deposits first, then trading, then withdrawals.

## Severity 1: Hot Wallet Key Compromise

1. Set affected `custody_wallets.status='COMPROMISED'`.
2. Rotate KMS key with `rotateDueSecrets`.
3. Move remaining hot wallet funds to cold wallet using offline process.
4. Require multisig approval for all withdrawals.
5. Generate SAR if user funds were affected.

## Severity 1: Market Manipulation

1. Halt affected market in `market_circuit_breakers`.
2. Run wash-trade detector.
3. Export `clob_trades`, `clob_orders`, and compliance cases.
4. Resume market only after oracle median stabilizes.

## Severity 2: Transak Webhook Drift

1. Run `/api/exchange/reconcile`.
2. Inspect `webhook_events` failed rows.
3. Replay missing signed webhook payloads after JWT/HMAC verification.

## Required Evidence

- correlation IDs
- immutable audit log hash chain
- ledger transaction IDs
- Redis stream offsets
- affected KMS key versions
