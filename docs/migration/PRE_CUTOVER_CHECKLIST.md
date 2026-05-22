# NeoNoble Ramp - PostgreSQL Migration Pre-Cutover Checklist

## Migration Status
- **Current Phase**: `validation` / `dual_read_pg`
- **Mode**: Dual-write (MongoDB + PostgreSQL), reads from PostgreSQL
- **Rollback Available**: Yes - `/api/migration/rollback`

---

## 🔴 PHASE 1: Stability Validation (REQUIRED)

### 1.1 Continuous Stability Metrics
| Metric | Threshold | Current | Status |
|--------|-----------|---------|--------|
| Consistency Failures | 0 | ___ | ⬜ |
| Error Rate | < 0.1% | ___ | ⬜ |
| P99 Latency | < 500ms | ___ | ⬜ |
| Uptime | 100% | ___ | ⬜ |
| Observation Period | ≥ 24 hours | ___ | ⬜ |

### 1.2 Health Check Validation
```bash
# Run every 5 minutes during validation
curl -s $API_URL/api/migration/health
```
- [ ] `healthy: true` consistently
- [ ] `consistency_failures: 0` maintained
- [ ] No phase regression detected

---

## 🟠 PHASE 2: Lifecycle Integrity (REQUIRED)

### 2.1 Off-Ramp Lifecycle Validation
- [ ] QUOTE_CREATED → DEPOSIT_PENDING transition
- [ ] DEPOSIT_PENDING → DEPOSIT_DETECTED transition
- [ ] DEPOSIT_DETECTED → DEPOSIT_CONFIRMED transition
- [ ] DEPOSIT_CONFIRMED → SETTLEMENT_PENDING transition
- [ ] SETTLEMENT_PENDING → SETTLEMENT_PROCESSING transition
- [ ] SETTLEMENT_PROCESSING → SETTLEMENT_COMPLETED transition
- [ ] SETTLEMENT_COMPLETED → PAYOUT_INITIATED transition
- [ ] PAYOUT_INITIATED → PAYOUT_COMPLETED transition
- [ ] PAYOUT_COMPLETED → COMPLETED transition
- [ ] All 11 states in correct order ✅
- [ ] Timeline timestamps are monotonically increasing ✅
- [ ] Settlement calculations match expected values ✅

### 2.2 On-Ramp Lifecycle Validation
- [ ] QUOTE_CREATED → PAYMENT_PENDING transition
- [ ] PAYMENT_PENDING → PAYMENT_DETECTED transition
- [ ] PAYMENT_DETECTED → PAYMENT_CONFIRMED transition
- [ ] PAYMENT_CONFIRMED → CRYPTO_PENDING transition
- [ ] CRYPTO_PENDING → CRYPTO_PROCESSING transition
- [ ] CRYPTO_PROCESSING → CRYPTO_SENT transition
- [ ] CRYPTO_SENT → DELIVERY_CONFIRMED transition
- [ ] DELIVERY_CONFIRMED → COMPLETED transition
- [ ] All 9 states in correct order ✅
- [ ] Timeline timestamps are monotonically increasing ✅
- [ ] Crypto amount calculations match expected values ✅

### 2.3 Concurrent Execution Validation
- [ ] 5+ simultaneous off-ramp transactions complete successfully
- [ ] 5+ simultaneous on-ramp transactions complete successfully
- [ ] No state corruption under concurrent load
- [ ] No duplicate timeline events
- [ ] No orphan or partial writes

---

## 🟡 PHASE 3: Data Integrity (REQUIRED)

### 3.1 Audit Trail Verification
- [ ] All transactions have complete audit logs
- [ ] Audit log timestamps match transaction timeline
- [ ] Event types correctly recorded
- [ ] No missing audit entries
- [ ] Settlement IDs properly linked

### 3.2 UTC Timestamp Validation
- [ ] All `created_at` timestamps are UTC-normalized
- [ ] All `completed_at` timestamps are UTC-normalized
- [ ] Timeline event timestamps are UTC-normalized
- [ ] No timezone drift between MongoDB and PostgreSQL
- [ ] Timestamp delta tolerance < 1 second

### 3.3 Settlement Chain Consistency
- [ ] Settlement amounts match transaction net_payout
- [ ] Settlement IDs are unique
- [ ] Settlement status aligns with transaction state
- [ ] Payout references are generated correctly
- [ ] Fee calculations are consistent (1.5%)

---

## 🟢 PHASE 4: Integration Validation (REQUIRED)

### 4.1 Webhook Delivery Verification
- [ ] Webhook events are queued correctly
- [ ] Delivery attempts succeed within retry limits
- [ ] HMAC signatures are valid
- [ ] Event payloads contain all required fields
- [ ] No duplicate deliveries

### 4.2 Developer API (HMAC) Validation
- [ ] API key authentication works
- [ ] HMAC signature validation works
- [ ] Quote creation via HMAC works
- [ ] Transaction retrieval via HMAC works
- [ ] Timeline retrieval via HMAC works

### 4.3 User API (JWT) Validation
- [ ] User registration creates dual-write
- [ ] User login reads from PostgreSQL
- [ ] Quote creation writes to both databases
- [ ] Transaction retrieval reads from PostgreSQL
- [ ] Timeline retrieval reads from PostgreSQL

---

## 🔵 PHASE 5: Pre-Cutover Sign-Off

### 5.1 Final Validation Script
```bash
curl -s -X POST $API_URL/api/migration/validate
```
- [ ] All validation checks pass
- [ ] Record counts match between databases
- [ ] Recent transactions verified
- [ ] State consistency confirmed

### 5.2 Metrics Review
```bash
curl -s $API_URL/api/migration/metrics
```
- [ ] `consistency_rate: 100%`
- [ ] `consistency_failures: 0`
- [ ] Write counts show balanced dual-write

### 5.3 Final Sign-Off Criteria
- [ ] All Phase 1-4 checks completed ✅
- [ ] Minimum 24-hour observation period completed ✅
- [ ] Zero consistency failures during observation ✅
- [ ] User verification of UI flows completed ✅
- [ ] Developer API verification completed ✅
- [ ] Rollback procedure documented and tested ✅

---

## ⚡ CUTOVER EXECUTION

### When ALL above criteria are met:
```bash
# Execute final cutover
curl -s -X POST $API_URL/api/migration/complete
```

### Expected Response:
```json
{
  "message": "Migration completed - PostgreSQL only mode",
  "phase": "completed",
  "mode": "postgresql_only",
  "completed_at": "2026-01-XX..."
}
```

---

## 🚨 ROLLBACK PROCEDURE (Emergency)

If any critical issue is detected:
```bash
curl -s -X POST "$API_URL/api/migration/rollback?reason=<REASON>"
```

Rollback is available until `/api/migration/complete` is executed.

---

## Approval Signatures

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Technical Lead | ___ | ___ | ⬜ |
| Operations | ___ | ___ | ⬜ |
| Product Owner | ___ | ___ | ⬜ |
