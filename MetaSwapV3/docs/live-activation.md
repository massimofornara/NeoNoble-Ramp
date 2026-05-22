# Live Activation

MetaSwapV3 is complete at the software and internal operations layer. Live activation is the controlled connection of regulated production credentials and endpoints.

## Required Inputs

Populate `.env.production` from `.env.production.example` with:

- Banking API URL, API key and HMAC secret.
- Card/PSP API URL, API key and HMAC secret.
- Custody/MPC/HSM API URL, API key and HMAC secret.
- Market maker, hedging, AML and Travel Rule endpoints and secrets.
- Mainnet RPC provider lists for Ethereum, BNB Chain, Solana, Base and Polygon.
- Token factory or Solana token program addresses.
- `ADMIN_API_KEY`.
- `INTERNAL_HSM_MASTER_KEY`.

## Activation Command

```powershell
powershell -ExecutionPolicy Bypass -File scripts/live-activation.ps1 -EnvFile .env.production -LoadRequests 1000 -LoadConcurrency 25
```

The activation command:

1. Loads production environment variables.
2. Enforces that every regulated terminal credential is present.
3. Starts MetaSwapV3 in production mode.
4. Runs production readiness, security baseline and load test.
5. Verifies providers, regions and RPC chains.
6. Generates SOC2, MiCA/CASP, EMI/PI and BSA/AML evidence packages.
7. Stops the validation process cleanly.

If any credential, endpoint, RPC, token factory address, admin key or HSM key is missing, activation fails closed before go-live.

## Completion Criteria

Activation is complete only when the command returns:

```json
{
  "status": "LIVE_ACTIVATION_VALIDATED"
}
```

No software change is required after this point.
