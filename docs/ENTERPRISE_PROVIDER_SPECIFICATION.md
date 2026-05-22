# NeoNoble Ramp - Enterprise Provider Specification

## Overview

NeoNoble Ramp operates as a **Provider-of-Record (PoR)** platform, functioning as a Merchant-of-Record style liquidity provider for cryptocurrency on/off-ramp services. This document outlines the enterprise-grade specifications for compliance, event broadcasting, and partner integration.

---

## 1. KYC/AML Responsibility Model

### 1.1 PoR Responsibility Framework

NeoNoble Ramp assumes **full compliance responsibility** as the Provider-of-Record:

| Compliance Area | Responsibility | Provider |
|-----------------|----------------|----------|
| KYC Verification | PoR | `internal_por` |
| AML Screening | PoR | `internal_por` |
| Transaction Monitoring | PoR | `internal_por` |
| Risk Assessment | PoR | `internal_por` |
| Regulatory Reporting | PoR | Platform |

### 1.2 Compliance States

```typescript
enum KYCStatus {
  NOT_REQUIRED = "not_required"  // PoR handles KYC
  PENDING = "pending"            // Future: User verification pending
  VERIFIED = "verified"          // Future: User KYC verified
  REJECTED = "rejected"          // Future: KYC rejected
  EXPIRED = "expired"            // Future: KYC expired
}

enum AMLStatus {
  NOT_REQUIRED = "not_required"  // PoR handles AML
  PENDING = "pending"            // Future: AML screening pending
  CLEARED = "cleared"            // Transaction cleared
  FLAGGED = "flagged"            // Future: Transaction flagged
  BLOCKED = "blocked"            // Future: Transaction blocked
}
```

### 1.3 Compliance Metadata

Every transaction includes compliance information:

```json
{
  "compliance": {
    "kyc_status": "not_required",
    "kyc_provider": "internal_por",
    "kyc_verified_at": null,
    "aml_status": "cleared",
    "aml_provider": "internal_por",
    "aml_cleared_at": "2025-01-06T12:00:00Z",
    "risk_score": 0.0,
    "risk_level": "low",
    "por_responsible": true
  }
}
```

### 1.4 Future KYC Integration Points

For enhanced compliance (e.g., enterprise customers), the platform supports:

- **Identity Verification Providers**: Jumio, Onfido, Veriff
- **AML Screening Providers**: Chainalysis, Elliptic, CipherTrace
- **Risk Scoring**: Real-time transaction risk assessment

---

## 2. Webhook Event Delivery Model

### 2.1 Event Types

NeoNoble Ramp broadcasts events for all transaction state transitions:

#### On-Ramp Events (Fiat → Crypto)
| Event | State | Description |
|-------|-------|-------------|
| `onramp.quote.created` | QUOTE_CREATED | Quote generated |
| `onramp.quote.accepted` | QUOTE_ACCEPTED | User accepted quote |
| `onramp.payment.pending` | PAYMENT_PENDING | Awaiting fiat payment |
| `onramp.payment.detected` | PAYMENT_DETECTED | Fiat payment detected |
| `onramp.payment.confirmed` | PAYMENT_CONFIRMED | Fiat payment confirmed |
| `onramp.crypto.sending` | CRYPTO_SENDING | Crypto delivery initiated |
| `onramp.crypto.sent` | CRYPTO_SENT | Crypto transaction broadcast |
| `onramp.crypto.confirmed` | CRYPTO_CONFIRMED | Crypto delivery confirmed |
| `onramp.completed` | COMPLETED | Transaction complete |
| `onramp.failed` | FAILED | Transaction failed |

#### Off-Ramp Events (Crypto → Fiat)
| Event | State | Description |
|-------|-------|-------------|
| `offramp.quote.created` | QUOTE_CREATED | Quote generated |
| `offramp.quote.accepted` | QUOTE_ACCEPTED | User accepted quote |
| `offramp.deposit.pending` | DEPOSIT_PENDING | Awaiting crypto deposit |
| `offramp.deposit.detected` | DEPOSIT_DETECTED | Crypto deposit detected |
| `offramp.deposit.confirmed` | DEPOSIT_CONFIRMED | Crypto deposit confirmed |
| `offramp.settlement.pending` | SETTLEMENT_PENDING | Settlement initiated |
| `offramp.settlement.processing` | SETTLEMENT_PROCESSING | Settlement processing |
| `offramp.settlement.completed` | SETTLEMENT_COMPLETED | Settlement complete |
| `offramp.payout.initiated` | PAYOUT_INITIATED | Fiat payout initiated |
| `offramp.payout.completed` | PAYOUT_COMPLETED | Fiat payout complete |
| `offramp.completed` | COMPLETED | Transaction complete |
| `offramp.failed` | FAILED | Transaction failed |

### 2.2 Webhook Payload Structure

```json
{
  "event_id": "evt_abc123",
  "event_type": "onramp.payment.confirmed",
  "timestamp": "2025-01-06T12:00:00Z",
  "api_version": "2.0.0",
  "data": {
    "quote_id": "por_on_abc123",
    "direction": "onramp",
    "state": "PAYMENT_CONFIRMED",
    "crypto_amount": 0.985,
    "crypto_currency": "NENO",
    "fiat_amount": 10000.0,
    "fiat_currency": "EUR",
    "exchange_rate": 10000,
    "fee_amount": 150.0,
    "fee_percentage": 1.5,
    "compliance": {
      "por_responsible": true,
      "aml_status": "cleared"
    },
    "metadata": {
      "user_id": "user_123",
      "api_key_id": "key_456"
    }
  },
  "previous_state": "PAYMENT_DETECTED"
}
```

### 2.3 Webhook Configuration (Future)

```json
{
  "webhook_url": "https://partner.example.com/webhooks/neonoble",
  "events": ["onramp.*", "offramp.completed"],
  "secret": "whsec_...",
  "enabled": true,
  "retry_policy": {
    "max_retries": 5,
    "retry_delays": [30, 60, 300, 900, 3600]
  }
}
```

### 2.4 Webhook Security

- **HMAC Signature**: All webhooks signed with `X-NeoNoble-Signature` header
- **Timestamp Validation**: `X-NeoNoble-Timestamp` header for replay protection
- **TLS 1.2+**: All webhook deliveries over HTTPS

---

## 3. Partner Integration Mode

### 3.1 External Provider Compatibility

NeoNoble Ramp is designed to integrate with external liquidity providers:

| Provider | Type | Status |
|----------|------|--------|
| **Internal PoR** | Built-in | ✅ Active |
| Transak | External | 🔜 Planned |
| MoonPay | External | 🔜 Planned |
| Ramp Network | External | 🔜 Planned |
| Banxa | External | 🔜 Planned |

### 3.2 Provider Interface

All providers implement a standard interface:

```python
class BaseProvider(ABC):
    @abstractmethod
    async def create_quote(...) -> ProviderQuote
    
    @abstractmethod
    async def accept_quote(...) -> ProviderQuote
    
    @abstractmethod
    async def process_deposit(...) -> ProviderQuote  # Off-ramp
    
    @abstractmethod
    async def process_payment(...) -> ProviderQuote  # On-ramp
    
    @abstractmethod
    async def execute_settlement(...) -> SettlementResult
    
    @abstractmethod
    async def get_transaction(...) -> ProviderQuote
```

### 3.3 Provider Configuration

```json
{
  "provider_type": "internal_por",
  "name": "NeoNoble Internal PoR",
  "enabled": true,
  "settlement_mode": "instant",
  "fee_percentage": 1.5,
  "min_amount_eur": 10.0,
  "max_amount_eur": 100000000.0,
  "supported_currencies": ["EUR"],
  "supported_cryptos": ["NENO", "BTC", "ETH", "USDT", "USDC", "BNB", "SOL"],
  "kyc_required": false,
  "aml_required": false
}
```

### 3.4 Settlement Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `instant` | Immediate completion | Default for PoR |
| `simulated_delay` | 1-3 day realistic delay | Testing/Demo |
| `batch` | Scheduled batch processing | Enterprise |

### 3.5 Multi-Provider Routing (Future)

```json
{
  "routing_rules": [
    {
      "condition": "amount > 50000 EUR",
      "provider": "transak"
    },
    {
      "condition": "crypto == 'BTC'",
      "provider": "moonpay"
    },
    {
      "condition": "default",
      "provider": "internal_por"
    }
  ]
}
```

---

## 4. API Authentication Models

### 4.1 User Authentication (JWT)

For end-user UI flows:

```
Authorization: Bearer eyJhbGciOiJIUzI1NiIs...
```

### 4.2 Developer Authentication (HMAC)

For platform API integration:

```
X-API-KEY: ak_live_abc123
X-TIMESTAMP: 1704528000
X-SIGNATURE: HMAC-SHA256(timestamp + body, api_secret)
```

### 4.3 Webhook Verification

For incoming webhooks:

```python
expected = hmac.new(
    webhook_secret.encode(),
    f"{timestamp}.{payload}".encode(),
    hashlib.sha256
).hexdigest()
```

---

## 5. Rate Limits & Quotas

### 5.1 API Rate Limits

| Endpoint Type | Rate Limit |
|---------------|------------|
| Quote Creation | 60/minute |
| Quote Execution | 30/minute |
| Transaction Status | 120/minute |
| Webhook Registration | 10/minute |

### 5.2 Transaction Limits

| Limit Type | Value |
|------------|-------|
| Minimum Transaction | €10 |
| Maximum Transaction | €100,000,000 |
| Daily Volume (User) | Configurable |
| Daily Volume (API Key) | Configurable |

---

## 6. Transaction Timeline

### 6.1 On-Ramp Timeline (Instant Mode)

```
QUOTE_CREATED (T+0s)
    ↓
QUOTE_ACCEPTED (T+0s)
    ↓
PAYMENT_PENDING (T+0s)
    ↓
PAYMENT_DETECTED (T+variable)  [Fiat payment received]
    ↓
PAYMENT_CONFIRMED (T+0s)
    ↓
CRYPTO_SENDING (T+0s)
    ↓
CRYPTO_SENT (T+0s)
    ↓
CRYPTO_CONFIRMED (T+0s)
    ↓
COMPLETED (T+0s)
```

### 6.2 Off-Ramp Timeline (Instant Mode)

```
QUOTE_CREATED (T+0s)
    ↓
QUOTE_ACCEPTED (T+0s)
    ↓
DEPOSIT_PENDING (T+0s)
    ↓
DEPOSIT_DETECTED (T+variable)  [Crypto deposit received]
    ↓
DEPOSIT_CONFIRMED (T+0s)
    ↓
SETTLEMENT_PENDING (T+0s)
    ↓
SETTLEMENT_PROCESSING (T+0s)
    ↓
SETTLEMENT_COMPLETED (T+0s)
    ↓
PAYOUT_INITIATED (T+0s)
    ↓
PAYOUT_COMPLETED (T+0s)
    ↓
COMPLETED (T+0s)
```

---

## 7. Error Handling

### 7.1 Error Response Format

```json
{
  "error": {
    "code": "QUOTE_EXPIRED",
    "message": "Quote has expired",
    "details": {
      "quote_id": "por_abc123",
      "expired_at": "2025-01-06T12:00:00Z"
    }
  }
}
```

### 7.2 Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `QUOTE_NOT_FOUND` | 404 | Quote does not exist |
| `QUOTE_EXPIRED` | 400 | Quote TTL exceeded |
| `INVALID_STATE` | 400 | Invalid state transition |
| `AMOUNT_MISMATCH` | 400 | Payment/deposit amount mismatch |
| `AUTH_FAILED` | 401 | Authentication failed |
| `RATE_LIMITED` | 429 | Rate limit exceeded |
| `PROVIDER_ERROR` | 503 | Provider unavailable |

---

## 8. Supported Assets

### 8.1 Cryptocurrencies

| Symbol | Name | Fixed Price |
|--------|------|-------------|
| NENO | NeoNoble Token | €10,000 |
| BTC | Bitcoin | Market Price |
| ETH | Ethereum | Market Price |
| USDT | Tether USD | Market Price |
| USDC | USD Coin | Market Price |
| BNB | Binance Coin | Market Price |
| SOL | Solana | Market Price |

### 8.2 Fiat Currencies

| Currency | Supported |
|----------|-----------|
| EUR | ✅ |
| USD | 🔜 Planned |
| GBP | 🔜 Planned |

---

## 9. Contact & Support

- **Technical Support**: support@neonoble.com
- **API Documentation**: /docs (Swagger UI)
- **Status Page**: /api/health

---

*Document Version: 2.0.0*  
*Last Updated: January 2025*
