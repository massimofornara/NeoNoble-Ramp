# NeoNoble PoR Engine - Technical Documentation

## Overview

The NeoNoble Provider-of-Record (PoR) Engine is an enterprise-grade, autonomous liquidity provider for cryptocurrency off-ramp transactions. It operates like production providers such as Transak, MoonPay, Ramp Network, and Banxa.

**Version:** 2.0.0  
**Settlement Mode:** Instant (default)  
**Liquidity:** Unlimited (€100M virtual pool)  
**NENO Price:** €10,000 (fixed)  
**Fee:** 1.5%

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     NeoNoble Platform                        │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │   User UI   │  │ Developer   │  │   Direct PoR API    │  │
│  │  (JWT Auth) │  │ API (HMAC)  │  │   (Optional Auth)   │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │                │                     │            │
│         └────────────────┼─────────────────────┘            │
│                          ▼                                  │
│              ┌───────────────────────┐                      │
│              │    PoR Engine Core    │                      │
│              │  (InternalPoRProvider)│                      │
│              └───────────┬───────────┘                      │
│                          │                                  │
│         ┌────────────────┼────────────────┐                 │
│         ▼                ▼                ▼                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │   Wallet    │  │ Settlement  │  │   Audit     │         │
│  │   Service   │  │   Service   │  │   Logger    │         │
│  └─────────────┘  └─────────────┘  └─────────────┘         │
│         │                                                   │
│         ▼                                                   │
│  ┌─────────────┐                                           │
│  │ Blockchain  │                                           │
│  │  Listener   │                                           │
│  └─────────────┘                                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Transaction Lifecycle States

| State | Description | Next States |
|-------|-------------|-------------|
| `QUOTE_CREATED` | Initial quote generated | QUOTE_ACCEPTED, QUOTE_EXPIRED |
| `QUOTE_ACCEPTED` | User accepted, awaiting deposit | DEPOSIT_PENDING |
| `DEPOSIT_PENDING` | Waiting for crypto deposit | DEPOSIT_DETECTED |
| `DEPOSIT_DETECTED` | Deposit seen on-chain | DEPOSIT_CONFIRMED, DEPOSIT_FAILED |
| `DEPOSIT_CONFIRMED` | Deposit has sufficient confirmations | SETTLEMENT_PENDING |
| `SETTLEMENT_PENDING` | Settlement initiated | SETTLEMENT_PROCESSING |
| `SETTLEMENT_PROCESSING` | Settlement being processed | SETTLEMENT_COMPLETED |
| `SETTLEMENT_COMPLETED` | Settlement done, payout ready | PAYOUT_INITIATED |
| `PAYOUT_INITIATED` | Bank transfer initiated | PAYOUT_COMPLETED |
| `PAYOUT_COMPLETED` | Bank transfer done | COMPLETED |
| `COMPLETED` | Transaction fully complete | (final) |
| `FAILED` | Transaction failed | (final) |
| `REFUNDED` | Transaction refunded | (final) |

---

## API Endpoints

### User UI Endpoints (JWT Authentication)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/ramp/offramp/quote` | Create off-ramp quote |
| POST | `/api/ramp/offramp/execute` | Accept and execute quote |
| POST | `/api/ramp/offramp/deposit/process` | Process deposit confirmation |
| GET | `/api/ramp/offramp/transaction/{quote_id}` | Get transaction details |
| GET | `/api/ramp/offramp/transaction/{quote_id}/timeline` | Get event timeline |
| GET | `/api/ramp/offramp/transactions` | List user transactions |

### Developer API Endpoints (HMAC Authentication)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/ramp-api-offramp-quote` | Create off-ramp quote |
| POST | `/api/ramp-api-offramp` | Execute off-ramp |
| POST | `/api/ramp-api-deposit-process` | Process deposit |
| GET | `/api/ramp-api-transaction/{quote_id}` | Get transaction |
| GET | `/api/ramp-api-transaction/{quote_id}/timeline` | Get timeline |
| GET | `/api/ramp-api-transactions` | List transactions |

### Direct PoR API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/por/status` | PoR engine status |
| POST | `/api/por/quote` | Create quote |
| POST | `/api/por/quote/accept` | Accept quote |
| POST | `/api/por/deposit/process` | Process deposit |
| GET | `/api/por/transaction/{quote_id}` | Get transaction |
| GET | `/api/por/transaction/{quote_id}/timeline` | Get timeline |
| GET | `/api/por/transactions` | List transactions |
| GET | `/api/por/liquidity` | Liquidity status |
| POST | `/api/por/config/settlement-mode` | Configure settlement |

### Monitoring Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/monitoring/health` | System health |
| GET | `/api/monitoring/metrics` | PoR metrics |
| GET | `/api/monitoring/audit/trail/{quote_id}` | Audit trail |
| GET | `/api/monitoring/audit/events` | Recent audit events |
| GET | `/api/monitoring/config` | System config |

---

## Request/Response Schemas

### Create Quote Request
```json
{
  "crypto_amount": 1.0,
  "crypto_currency": "NENO",
  "bank_account": "IT22B0200822800000103317304"  // optional
}
```

### Quote Response
```json
{
  "quote_id": "por_abc123def456",
  "provider": "internal_por",
  "crypto_amount": 1.0,
  "crypto_currency": "NENO",
  "fiat_amount": 10000.0,
  "fiat_currency": "EUR",
  "exchange_rate": 10000.0,
  "fee_amount": 150.0,
  "fee_percentage": 1.5,
  "net_payout": 9850.0,
  "deposit_address": "0x1234...abcd",
  "expires_at": "2024-01-01T12:00:00+00:00",
  "created_at": "2024-01-01T11:00:00+00:00",
  "state": "QUOTE_CREATED",
  "compliance": {
    "kyc_status": "not_required",
    "kyc_provider": "internal_por",
    "aml_status": "not_required",
    "aml_provider": "internal_por",
    "por_responsible": true,
    "risk_level": "low"
  },
  "timeline": [
    {
      "timestamp": "2024-01-01T11:00:00+00:00",
      "state": "QUOTE_CREATED",
      "message": "Off-ramp quote created by PoR engine",
      "provider": "internal_por"
    }
  ],
  "metadata": {
    "por_engine": "NeoNoble Internal PoR",
    "settlement_mode": "instant"
  }
}
```

### Accept Quote Request
```json
{
  "quote_id": "por_abc123def456",
  "bank_account": "IT22B0200822800000103317304"
}
```

### Process Deposit Request
```json
{
  "quote_id": "por_abc123def456",
  "tx_hash": "0xabcdef123456...",
  "amount": 1.0
}
```

### Timeline Response
```json
{
  "quote_id": "por_abc123def456",
  "event_count": 11,
  "events": [
    {
      "timestamp": "2024-01-01T11:00:00+00:00",
      "state": "QUOTE_CREATED",
      "message": "Off-ramp quote created by PoR engine",
      "details": {...},
      "provider": "internal_por"
    },
    // ... 10 more events
    {
      "timestamp": "2024-01-01T11:05:00+00:00",
      "state": "COMPLETED",
      "message": "Off-ramp completed successfully",
      "details": {
        "settlement_id": "stl_xyz789",
        "payout_reference": "PAY-ABC123-20240101"
      },
      "provider": "internal_por"
    }
  ]
}
```

---

## HMAC Authentication (Developer API)

### Headers Required
```
X-API-KEY: <your_api_key>
X-TIMESTAMP: <unix_timestamp_seconds>
X-SIGNATURE: <hmac_sha256_signature>
Content-Type: application/json
```

### Signature Generation
```python
import hmac
import hashlib
import time
import json

def sign_request(body_dict, api_secret):
    timestamp = str(int(time.time()))
    body_str = json.dumps(body_dict, separators=(",", ":"))
    message = timestamp + body_str
    signature = hmac.new(
        api_secret.encode(),
        message.encode(),
        hashlib.sha256
    ).hexdigest()
    return timestamp, signature
```

### Example Request (Python)
```python
import httpx

body = {"crypto_amount": 1.0, "crypto_currency": "NENO"}
timestamp, signature = sign_request(body, API_SECRET)

response = httpx.post(
    "https://your-domain.com/api/ramp-api-offramp-quote",
    headers={
        "X-API-KEY": API_KEY,
        "X-TIMESTAMP": timestamp,
        "X-SIGNATURE": signature,
        "Content-Type": "application/json"
    },
    json=body
)
```

---

## Compliance Model

The PoR engine operates as the **Merchant-of-Record**, handling:

| Responsibility | Handler | Status |
|----------------|---------|--------|
| KYC Verification | PoR Engine | `not_required` (PoR handles) |
| AML Screening | PoR Engine | `cleared` (after deposit confirmation) |
| Risk Assessment | PoR Engine | `low` (default) |
| Regulatory Compliance | PoR Engine | PoR responsible |

### Compliance Fields in Response
```json
{
  "compliance": {
    "kyc_status": "not_required",
    "kyc_provider": "internal_por",
    "kyc_verified_at": null,
    "aml_status": "cleared",
    "aml_provider": "internal_por",
    "aml_cleared_at": "2024-01-01T11:03:00+00:00",
    "risk_score": 0.0,
    "risk_level": "low",
    "por_responsible": true
  }
}
```

---

## Settlement Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `instant` | Immediate settlement (default) | Production, real-time UX |
| `simulated_delay` | 1-3 day banking delay | Testing, realistic simulation |
| `batch` | Scheduled batch processing | High-volume operations |

### Configure Settlement Mode
```bash
curl -X POST /api/por/config/settlement-mode \
  -H "Content-Type: application/json" \
  -d '{"mode": "instant"}'
```

---

## E2E Test Sequence

```bash
# 1. Create Quote
curl -X POST /api/por/quote \
  -H "Content-Type: application/json" \
  -d '{"crypto_amount": 0.1, "crypto_currency": "NENO"}'
# Returns: quote_id, deposit_address

# 2. Accept Quote
curl -X POST /api/por/quote/accept \
  -H "Content-Type: application/json" \
  -d '{"quote_id": "por_xxx", "bank_account": "IT22B..."}'
# State: DEPOSIT_PENDING

# 3. Process Deposit (after blockchain confirmation)
curl -X POST /api/por/deposit/process \
  -H "Content-Type: application/json" \
  -d '{"quote_id": "por_xxx", "tx_hash": "0xabc...", "amount": 0.1}'
# State: COMPLETED (instant mode)

# 4. Verify Transaction
curl /api/por/transaction/por_xxx
# Returns: Full transaction with timeline

# 5. Check Timeline
curl /api/por/transaction/por_xxx/timeline
# Returns: 11 lifecycle events
```

---

## Monitoring & Observability

### Health Check
```bash
curl /api/monitoring/health
```

### Metrics
```bash
curl /api/monitoring/metrics
```

### Audit Trail
```bash
curl /api/monitoring/audit/trail/{quote_id}
```

### Audit Event Types
- `quote.created`, `quote.accepted`, `quote.expired`
- `deposit.pending`, `deposit.detected`, `deposit.confirmed`
- `settlement.initiated`, `settlement.completed`
- `payout.initiated`, `payout.completed`
- `compliance.aml_status_change`
- `system.startup`, `system.error`

---

## Error Handling

| HTTP Code | Meaning | Example |
|-----------|---------|--------|
| 400 | Bad Request | Invalid crypto currency |
| 404 | Not Found | Quote not found |
| 422 | Validation Error | Amount <= 0 |
| 503 | Service Unavailable | PoR engine not initialized |

### Error Response Format
```json
{
  "detail": "Unsupported cryptocurrency: INVALID_COIN"
}
```

---

## Known Limitations

1. **Bank Account Validation**: Currently accepts any format (IBAN validation planned)
2. **Quote Expiry**: Checked at accept time, not continuously
3. **External Providers**: Future integration points defined but not implemented

---

## Support

For technical support, contact the NeoNoble engineering team.
