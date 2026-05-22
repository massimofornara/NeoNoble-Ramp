# Revenue Distribution and Rapid Scale Runbook

Goal: route captured platform revenue to configured crypto and fiat destinations, then scale MetaSwapV3 API capacity quickly.

## Revenue Destinations

Crypto destination:

- `REVENUE_CRYPTO_WALLET=0xD436E1FbDFFD0a538D0A44A93c0dD52f92221862`
- `REVENUE_CRYPTO_CHAIN=ethereum`

Fiat destinations:

- `REVENUE_FIAT_IBAN_1=IT22B0200822800000103317304`
- `REVENUE_FIAT_NAME_1=Massimo Fornara`
- `REVENUE_FIAT_SHARE_BPS_1=5000`
- `REVENUE_FIAT_IBAN_2=BE06967614820722`
- `REVENUE_FIAT_NAME_2=NeoNoble Company`
- `REVENUE_FIAT_SHARE_BPS_2=5000`

The system intentionally blocks payout if the beneficiary name is missing. Wise and SEPA payouts require a correct legal account holder name.

Automated sweep:

- `k8s/revenue-sweep-cronjob.yaml`
- `helm/metaswap-v3/templates/revenue-sweep-cronjob.yaml`

The job calls `/revenue/distribution/sweep` every 15 minutes, uses `concurrencyPolicy: Forbid`, and authenticates with `ADMIN_API_KEY` from `metaswap-production-secrets`.

Current scale target:

- `REVENUE_TARGET_MONTHLY_USD=1000000`
- `REVENUE_NEXT_TARGET_MONTHLY_USD=10000000`

## API

Check revenue distribution plan:

```http
GET /revenue/distribution/plan
```

Run sweep:

```http
POST /revenue/distribution/sweep
x-admin-api-key: <ADMIN_API_KEY>
Content-Type: application/json
```

```json
{
  "asset": "EUR",
  "maxAmount": 1000
}
```

The sweep only moves funds after the external rail accepts the instruction.

## Rapid Scale

1. Build and push image:

```powershell
docker build -t metaswap-v3-core:1.0.6 .
```

2. Apply secrets with real provider credentials and revenue destination variables.

3. Deploy:

```powershell
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/secret.example.yaml
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/hpa.yaml
kubectl apply -f k8s/pdb.yaml
kubectl apply -f k8s/revenue-sweep-cronjob.yaml
```

4. Verify:

```powershell
kubectl -n metaswap get pods
kubectl -n metaswap get hpa
```

5. Run local readiness snapshot:

```powershell
npm run scale:local
```

## Production Gates

- No fake revenue sweep.
- No fiat payout without beneficiary name.
- No crypto sweep without live custody broadcaster and on-chain reserves.
- No scale campaign with guaranteed-profit claims.
