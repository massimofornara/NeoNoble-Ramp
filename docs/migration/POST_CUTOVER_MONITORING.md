# NeoNoble Ramp - Post-Cutover Monitoring & Operations Plan

---

## 📊 Real-Time Monitoring Dashboard

### Critical Health Endpoints

```bash
# System Health Check (every 1 minute)
curl -s $API_URL/api/monitoring/health

# Migration Status (every 5 minutes)
curl -s $API_URL/api/migration/status

# Migration Metrics (every 5 minutes)
curl -s $API_URL/api/migration/metrics
```

---

## 🎯 Key Performance Indicators (KPIs)

### Tier 1: Critical (Immediate Alert)
| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| Error Rate | < 0.1% | 0.1-1% | > 1% |
| P99 Latency | < 500ms | 500-1000ms | > 1000ms |
| Transaction Success Rate | > 99.9% | 99-99.9% | < 99% |
| Database Connection Pool | < 80% | 80-90% | > 90% |
| Settlement Success Rate | 100% | 99-100% | < 99% |

### Tier 2: Warning (15-minute Response)
| Metric | Healthy | Warning | Action |
|--------|---------|---------|--------|
| Webhook Delivery Rate | > 99% | 95-99% | Investigate retry queue |
| Audit Log Completeness | 100% | 99-100% | Check logging pipeline |
| API Response Time (avg) | < 200ms | 200-400ms | Review slow queries |
| Memory Usage | < 70% | 70-85% | Monitor for leak |

### Tier 3: Informational (Daily Review)
| Metric | Expected | Action if Deviation |
|--------|----------|---------------------|
| Daily Transaction Volume | Baseline ±20% | Capacity planning |
| New User Registrations | Baseline ±30% | Marketing review |
| API Key Usage | Baseline ±25% | Partner engagement |

---

## 🔔 Alert Thresholds

### Immediate Escalation (P0)
- Any database connection failure
- Transaction state corruption detected
- Settlement calculation mismatch
- Audit log gap detected
- 3+ consecutive webhook delivery failures

### High Priority (P1)
- Error rate exceeds 0.5%
- P99 latency exceeds 1 second
- Memory usage exceeds 85%
- Unusual transaction pattern detected

### Standard (P2)
- Minor latency increase
- Non-critical endpoint errors
- Retry queue backlog

---

## 🔍 Lifecycle Anomaly Detection

### State Transition Monitoring
```sql
-- Check for stuck transactions (PostgreSQL)
SELECT quote_id, state, created_at, 
       EXTRACT(EPOCH FROM (NOW() - created_at))/60 as minutes_in_state
FROM transactions 
WHERE state NOT IN ('COMPLETED', 'FAILED', 'EXPIRED')
  AND created_at < NOW() - INTERVAL '30 minutes'
ORDER BY created_at;
```

### Expected State Durations
| State | Expected Duration | Alert Threshold |
|-------|-------------------|----------------|
| QUOTE_CREATED | < 60 min | 65 min |
| DEPOSIT_PENDING | < 30 min | 35 min |
| PAYMENT_PENDING | < 30 min | 35 min |
| SETTLEMENT_PROCESSING | < 5 min | 10 min |

### Anomaly Indicators
- [ ] Transaction stuck in intermediate state > threshold
- [ ] Timeline events out of order
- [ ] Duplicate state transitions
- [ ] Missing timeline events
- [ ] Settlement without completed transaction

---

## 📦 Webhook Delivery Reliability

### Thresholds
| Metric | Healthy | Warning | Critical |
|--------|---------|---------|----------|
| First Attempt Success | > 95% | 90-95% | < 90% |
| Final Delivery Rate | > 99% | 97-99% | < 97% |
| Retry Queue Depth | < 50 | 50-200 | > 200 |
| Avg Delivery Time | < 5s | 5-15s | > 15s |

### Monitoring Query
```sql
-- Webhook delivery status (PostgreSQL)
SELECT status, COUNT(*) as count,
       AVG(attempt) as avg_attempts
FROM webhook_deliveries 
WHERE created_at > NOW() - INTERVAL '1 hour'
GROUP BY status;
```

---

## 📋 Observation Period Schedule

### Day 1-3: Intensive Monitoring
- Health check: Every 1 minute
- Metrics review: Every 15 minutes
- Manual validation: Every 2 hours
- Engineering standby: 24/7

### Day 4-7: Standard Monitoring
- Health check: Every 5 minutes
- Metrics review: Every hour
- Manual validation: Every 8 hours
- Engineering standby: Business hours + on-call

### Day 8+: Normal Operations
- Health check: Every 5 minutes (automated)
- Metrics review: Daily summary
- Manual validation: Weekly
- Engineering: Standard on-call rotation

---

## 🚨 Incident Response Procedures

### Severity 1 (Critical)
1. **Immediate Actions**:
   - Page on-call engineer
   - Assess impact scope
   - Consider traffic pause if data integrity at risk

2. **Investigation**:
   - Check `/api/migration/health`
   - Review recent transactions
   - Check database connectivity
   - Review error logs

3. **Communication**:
   - Internal: Slack/PagerDuty
   - External: Status page update (if user-facing)

### Severity 2 (High)
1. **Actions**:
   - Alert engineering team
   - Begin investigation within 15 minutes
   - Document findings

2. **Resolution**:
   - Implement fix
   - Verify resolution
   - Post-incident review within 24 hours

---

## 🔧 Maintenance Windows

### Scheduled Maintenance
- **Time**: [TO BE DEFINED] (lowest traffic period)
- **Duration**: Maximum 30 minutes
- **Notice**: 24 hours advance

### Emergency Maintenance
- **Authority**: Engineering Lead or higher
- **Notice**: As soon as possible
- **Communication**: Status page + direct notification

---

## 📈 Performance Baseline

### Pre-Migration Baseline
| Metric | Value | Date |
|--------|-------|------|
| Avg Response Time | ___ ms | ___ |
| P99 Latency | ___ ms | ___ |
| Daily Transactions | ___ | ___ |
| Error Rate | ___ % | ___ |

### Post-Migration Target
| Metric | Target | Acceptable Range |
|--------|--------|------------------|
| Avg Response Time | ≤ Pre-migration | +10% |
| P99 Latency | ≤ Pre-migration | +15% |
| Daily Transactions | ≥ Pre-migration | -5% |
| Error Rate | ≤ Pre-migration | +0.05% |

---

## ✅ Final Closure Criteria

Before closing the observation period:

- [ ] 7 consecutive days with zero critical incidents
- [ ] All KPIs within healthy thresholds
- [ ] No lifecycle anomalies detected
- [ ] Webhook delivery rate > 99%
- [ ] User feedback: No migration-related issues reported
- [ ] Performance baseline maintained or improved
- [ ] Backup and recovery procedures verified
- [ ] Documentation updated and reviewed

---

**Document Version**: 1.0
**Last Updated**: [DATE]
**Owner**: Engineering Team
