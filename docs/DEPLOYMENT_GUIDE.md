# NeoNoble PoR Engine - Production Deployment Guide

## Overview

This guide covers production deployment of the NeoNoble PoR Engine on Emergent platform.

---

## Pre-Deployment Checklist

### 1. Environment Variables

The PoR engine operates **autonomously** without requiring external credentials. However, the following can be configured:

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `MONGO_URL` | Auto | MongoDB connection (Emergent provides) | Auto-injected |
| `DB_NAME` | No | Database name | `neonoble_ramp` |
| `QUOTE_TTL_MINUTES` | No | Quote expiry time | `60` |
| `BSC_RPC_URL` | Optional | BSC RPC for blockchain monitoring | Disabled if not set |
| `NENO_CONTRACT_ADDRESS` | Optional | NENO token contract | Default provided |
| `NENO_WALLET_MNEMONIC` | Optional | HD wallet for deposit addresses | Disabled if not set |
| `STRIPE_SECRET_KEY` | Optional | Stripe for additional payouts | Disabled if not set |

### 2. Autonomous Operation

The PoR engine requires **no credentials** for basic operation:
- ✅ Quote creation works without any config
- ✅ Settlement processing works (instant mode)
- ✅ Transaction lifecycle works
- ✅ Compliance metadata available

Optional features when credentials provided:
- 🔧 BSC blockchain monitoring (needs `BSC_RPC_URL`)
- 🔧 Unique deposit addresses (needs `NENO_WALLET_MNEMONIC`)
- 🔧 External Stripe payouts (needs `STRIPE_SECRET_KEY`)

---

## Deployment Steps

### Step 1: Verify Health Endpoints

```bash
# Main health check
curl https://your-domain.com/health
# Expected: {"status": "healthy", "service": "NeoNoble Ramp"}

# PoR status
curl https://your-domain.com/api/por/status
# Expected: provider info, liquidity status

# Monitoring health
curl https://your-domain.com/api/monitoring/health
# Expected: component status
```

### Step 2: Test Core Functionality

```bash
# Create test quote
curl -X POST https://your-domain.com/api/por/quote \
  -H "Content-Type: application/json" \
  -d '{"crypto_amount": 0.001, "crypto_currency": "NENO"}'

# Verify response includes:
# - quote_id
# - net_payout (€9.85 for 0.001 NENO)
# - state: QUOTE_CREATED
# - compliance: por_responsible = true
```

### Step 3: Configure Emergent Secrets (Optional)

If you need blockchain monitoring or wallet features:

1. Go to Emergent Dashboard → Secrets
2. Add the following secrets:
   - `BSC_RPC_URL`: Your BSC RPC endpoint
   - `NENO_WALLET_MNEMONIC`: HD wallet mnemonic
   - `NENO_CONTRACT_ADDRESS`: NENO token contract

### Step 4: Verify Full Flow

```bash
# Full E2E test
./scripts/e2e_test.py
```

---

## Monitoring & Operations

### Key Monitoring Endpoints

| Endpoint | Purpose | Frequency |
|----------|---------|----------|
| `/health` | Basic liveness | Every 30s |
| `/api/monitoring/health` | Component status | Every 1m |
| `/api/monitoring/metrics` | Business metrics | Every 5m |
| `/api/por/status` | PoR availability | Every 1m |

### Recommended Alerts

1. **PoR Engine Down**
   - Check: `/api/por/status` returns `available: false`
   - Severity: Critical

2. **High Error Rate**
   - Check: Monitor 400/500 responses
   - Severity: Warning at >1%, Critical at >5%

3. **Settlement Backlog**
   - Check: `/api/monitoring/metrics` → settlement.by_status.pending
   - Severity: Warning if >10 pending for >1 hour

### Log Monitoring

Structured JSON logs are emitted for:
- Transaction lifecycle events
- Settlement processing
- Compliance status changes
- System errors

Log format:
```json
{
  "timestamp": "2024-01-01T12:00:00+00:00",
  "event_type": "quote.created",
  "service": "por_engine",
  "quote_id": "por_xxx",
  "details": {...}
}
```

---

## Scaling Considerations

### Performance Characteristics

| Metric | Value |
|--------|-------|
| Quote creation | ~50-80ms avg |
| Full cycle (instant) | ~100-150ms |
| Concurrent capacity | 20+ requests/sec |
| Max liquidity | Unlimited (€100M pool) |

### Database Indexes

The following indexes are automatically created:
- `por_transactions.quote_id` (unique)
- `por_transactions.state`
- `por_transactions.user_id`
- `por_settlements.settlement_id` (unique)
- `audit_logs.timestamp`, `audit_logs.quote_id`

### Horizontal Scaling

The PoR engine is stateless and can be scaled horizontally:
- MongoDB handles all persistence
- No in-memory state between requests
- Background tasks (blockchain polling) should run on single instance

---

## Troubleshooting

### Common Issues

#### 1. PoR Engine Not Initialized
```
Error: "PoR engine not available"
```
**Solution**: Check MongoDB connection. The PoR engine initializes on startup.

#### 2. Blockchain Monitoring Not Working
```
Warning: "Blockchain listener disabled (no BSC_RPC_URL)"
```
**Solution**: Set `BSC_RPC_URL` environment variable.

#### 3. Deposit Addresses Not Generated
```
deposit_address: null
```
**Solution**: Set `NENO_WALLET_MNEMONIC` environment variable.

### Recovery Procedures

#### Restart Backend
```bash
# Via Emergent
Trigger redeployment from dashboard

# Verify recovery
curl /api/monitoring/health
```

#### Clear Stuck Transactions
Transactions in intermediate states will resume on restart. No manual intervention needed.

---

## Security Considerations

1. **API Keys**: Store in Emergent Secrets, never in code
2. **Mnemonic**: Critical secret - use Emergent Secrets only
3. **CORS**: Configured to allow all origins by default
4. **Rate Limiting**: Implement at load balancer level

---

## Support Contacts

For production issues, contact the NeoNoble engineering team.
