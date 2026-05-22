# Enterprise Operations

## Self-Hosted Operating Model

MetaSwap V3 owns the internal operating stack:

- Internal market making and RFQ quote generation.
- Treasury, inventory, capital allocation and exposure controls.
- Internal double-entry banking ledger.
- Proprietary AML, fraud, market surveillance and circuit breaker decisions.
- Direct Travel Rule message generation using IVMS101-shaped payloads.
- Custody policy orchestration with final signing routed through configured MPC/HSM infrastructure.
- Payout orchestration with bank/card networks treated as regulated final rails.

External providers are not authoritative for pricing, risk, balances, ledger state, market state or compliance decisions.

## Active-Active Deployment

- Run three or more API replicas per region.
- Partition matching-engine markets by symbol pair.
- Use one active writer per market partition and replayable event logs.
- Keep ledger writes strongly consistent inside the selected primary ledger region.
- Replicate immutable event and audit logs cross-region.
- Fail traffic through global load balancer health checks.

## Distributed Failover

- Banking rail down: payout instructions remain in reconciliation state and ledger funds stay traceable.
- Card rail down: card payouts pause; SEPA/SWIFT remain available if configured.
- Custody signer down: withdrawals move to policy-held state.
- External market maker down: internal market maker continues quoting within treasury limits.
- Blockchain RPC down: token deployment and withdrawal broadcast pause for affected chain only.

MetaSwapV3 exposes a multi-region control plane:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/regions/status
Invoke-RestMethod http://127.0.0.1:8080/regions/failover -Method Post -Headers @{"x-admin-api-key"=$env:ADMIN_API_KEY} -ContentType application/json -Body '{"fromRegion":"eu-west-primary","reason":"regional_network_partition"}'
```

## Event Replay

1. Restore ledger database.
2. Restore immutable event log.
3. Rebuild asset registry and balances.
4. Replay order, trade, ledger, payout and withdrawal events.
5. Recompute proof roots and compare with pre-incident root.

## Reconciliation

```powershell
Invoke-RestMethod http://127.0.0.1:8080/admin/reconcile -Method Post
```

Settlement is never considered final until both ledger and rail state are matched.

## Circuit Breakers

```powershell
Invoke-RestMethod http://127.0.0.1:8080/admin/markets/halt -Method Post -ContentType application/json -Body '{"market":"NBL-EUR","reason":"oracle_confidence_drop"}'
Invoke-RestMethod http://127.0.0.1:8080/admin/markets/resume -Method Post -ContentType application/json -Body '{"market":"NBL-EUR","reason":"risk_clear"}'
```

## Liquidity Stress

```powershell
Invoke-RestMethod http://127.0.0.1:8080/admin/stress-test -Method Post -ContentType application/json -Body '{"symbol":"NBL","shockPercent":0.35}'
```

## Provider Operations

Rail providers are hot-swappable terminal executors. Internal ledger, risk, treasury, pricing, Travel Rule and reconciliation remain authoritative.

```powershell
Invoke-RestMethod http://127.0.0.1:8080/providers
Invoke-RestMethod http://127.0.0.1:8080/providers/status -Method Post -Headers @{"x-admin-api-key"=$env:ADMIN_API_KEY} -ContentType application/json -Body '{"id":"primary-banking-rail","status":"paused","reason":"rail_maintenance"}'
```

## Regulatory Evidence

```powershell
Invoke-RestMethod http://127.0.0.1:8080/compliance/evidence/generate -Method Post -Headers @{"x-admin-api-key"=$env:ADMIN_API_KEY} -ContentType application/json -Body '{"control":"SOC2"}'
```
