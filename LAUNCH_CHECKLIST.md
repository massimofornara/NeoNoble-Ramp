# 🚀 NeoNoble Ramp - Production Launch Checklist

## Pre-Launch Validation

### ✅ Environment Configuration
- [ ] `.env` file configured with production values
- [ ] `PAYMENT_MODE=live` (if using real payments)
- [ ] Stripe live API keys configured
- [ ] BSC wallet funded with NENO tokens
- [ ] `NEXT_PUBLIC_BASE_URL` set to production domain
- [ ] `JWT_SECRET` is cryptographically secure (32+ chars)
- [ ] All secrets are unique (not from `.env.example`)

### ✅ Database Setup
- [ ] PostgreSQL 15+ running
- [ ] Database created: `neonoble_ramp`
- [ ] Migrations executed: `npx prisma migrate deploy`
- [ ] Platform client initialized: `node scripts/initDatabase.js`
- [ ] Database backup strategy in place

### ✅ Stripe Configuration
- [ ] Stripe account verified
- [ ] Live mode API keys obtained
- [ ] Webhook endpoint configured: `https://neonoble.it/api/webhooks/stripe`
- [ ] Webhook events selected:
  - `checkout.session.completed`
  - `checkout.session.async_payment_succeeded`
  - `checkout.session.async_payment_failed`
  - `payment_intent.succeeded`
  - `payment_intent.payment_failed`
- [ ] Webhook secret stored in `.env`
- [ ] Test webhook delivery in Stripe dashboard

### ✅ Blockchain Configuration
- [ ] BSC RPC provider accessible
- [ ] Platform wallet has private key set
- [ ] NENO contract address configured
- [ ] Wallet has sufficient NENO balance (recommended: 100+ NENO)
- [ ] Wallet has BSC (BNB) for gas fees (recommended: 0.1+ BNB)
- [ ] Contract is ERC-20 compliant with 18 decimals
- [ ] Test transaction sent successfully

### ✅ Security Hardening
- [ ] All API secrets are strong and unique
- [ ] HMAC signature validation working
- [ ] Nonce table created for replay protection
- [ ] Rate limiting configured (default: 1000 req/day)
- [ ] Fraud detection enabled
- [ ] SSL/TLS certificate installed
- [ ] Firewall rules configured
- [ ] Database access restricted to application only

## Production Validation

Run comprehensive validation:

```bash
node scripts/validate_production.js
```

**Expected output**: All checks passed, zero failures.

## Load Testing

Test system under load before launch:

```bash
# Set test credentials
export TEST_API_KEY="your-test-api-key"
export TEST_API_SECRET="your-test-api-secret"
export TEST_BASE_URL="https://neonoble.it"

# Run load test
export LOAD_TEST_CONCURRENCY=10
export LOAD_TEST_TOTAL=100
node scripts/load_test.js
```

**Success criteria**:
- Success rate ≥ 95%
- P95 latency < 1000ms
- No deadlocks or stuck sessions

## Deployment

### Step 1: Deploy Application

```bash
# Build production bundle
yarn build

# Start production server
yarn start

# Or use PM2 for process management
pm2 start yarn --name "neonoble-api" -- start
```

### Step 2: Start Background Workers

```bash
# Transaction worker
pm2 start workers/transactionWorker.js --name "neonoble-worker"

# Consistency reconciler
pm2 start workers/consistencyReconciler.js --name "neonoble-reconciler"

# Save PM2 configuration
pm2 save
pm2 startup
```

### Step 3: Configure Reverse Proxy (nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name neonoble.it;

    ssl_certificate /etc/letsencrypt/live/neonoble.it/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/neonoble.it/privkey.pem;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

### Step 4: Verify Services

```bash
# Check all services are running
pm2 status

# Check logs
pm2 logs neonoble-api
pm2 logs neonoble-worker
pm2 logs neonoble-reconciler

# Monitor real-time
pm2 monit
```

## Post-Launch Monitoring

### Health Checks

Monitor these endpoints:
- `GET /` - Homepage (should return 200)
- `GET /dev/login` - Dev portal (should return 200)
- `GET /ramp` - User ramp (should redirect to auth)

### Critical Metrics

**Application Metrics**:
- Request success rate ≥ 99%
- API latency P95 < 500ms
- Active sessions count
- Worker processing rate

**Business Metrics**:
- Successful onramp transactions
- Successful offramp transactions
- Total volume processed
- Average transaction size

**System Metrics**:
- CPU usage < 70%
- Memory usage < 80%
- Disk space > 20% free
- Database connections < 80% of pool

### Database Monitoring

```sql
-- Check session statuses
SELECT status, COUNT(*) 
FROM \"RampSession\" 
GROUP BY status;

-- Check stuck sessions
SELECT id, status, \"createdAt\", \"updatedAt\"
FROM \"RampSession\"
WHERE status IN ('AWAITING_PAYMENT', 'PAYMENT_CONFIRMED', 'CHAIN_PENDING')
AND \"updatedAt\" < NOW() - INTERVAL '30 minutes';

-- Check payment success rate
SELECT 
  COUNT(*) FILTER (WHERE status = 'COMPLETED') as completed,
  COUNT(*) FILTER (WHERE status = 'FAILED') as failed,
  COUNT(*) as total
FROM \"RampSession\"
WHERE \"createdAt\" > NOW() - INTERVAL '24 hours';
```

### Log Monitoring

```bash
# Application logs
tail -f /var/log/neonoble/api.log

# Worker logs
tail -f /var/log/neonoble/worker.log

# Reconciler logs
tail -f /var/log/neonoble/reconciler.log

# Stripe webhook logs
tail -f /var/log/neonoble/webhooks.log
```

## Incident Response

### Common Issues & Solutions

#### 1. Stuck Sessions

**Symptom**: Sessions remain in `PAYMENT_CONFIRMED` or `CHAIN_PENDING`

**Solution**:
```bash
# Restart consistency reconciler
pm2 restart neonoble-reconciler

# Manual reconciliation
node scripts/reconcile_sessions.js
```

#### 2. Stripe Webhook Failures

**Symptom**: Payments not confirming automatically

**Solution**:
1. Check webhook logs in Stripe dashboard
2. Verify webhook secret matches `.env`
3. Test webhook endpoint: `curl -X POST https://neonoble.it/api/webhooks/stripe`
4. Check `WebhookEvent` table for errors

#### 3. Blockchain Transaction Failures

**Symptom**: Tokens not sent after payment

**Solution**:
1. Check wallet balance: `node scripts/check_wallet.js`
2. Check RPC connectivity
3. Review gas price settings
4. Check nonce synchronization
5. Manual retry: Update session to `PAYMENT_CONFIRMED`

#### 4. High Rate Limit Rejections

**Symptom**: 429 errors increasing

**Solution**:
1. Identify problematic API clients
2. Review rate limit settings
3. Consider increasing limits for legitimate high-volume clients
4. Check for DDoS or abuse

#### 5. Database Connection Pool Exhausted

**Symptom**: "Too many connections" errors

**Solution**:
```bash
# Check active connections
psql -U neonoble -d neonoble_ramp -c "SELECT COUNT(*) FROM pg_stat_activity;"

# Restart application
pm2 restart all

# Increase pool size in DATABASE_URL if needed
```

## Rollback Procedure

If critical issues arise:

```bash
# 1. Stop accepting new transactions
pm2 stop neonoble-worker

# 2. Let existing transactions complete
# Wait 5-10 minutes, monitor dashboard

# 3. Stop application
pm2 stop neonoble-api

# 4. Restore database backup
pg_restore -U neonoble -d neonoble_ramp backup.dump

# 5. Revert code
git checkout <previous-stable-tag>
yarn build

# 6. Restart with previous version
pm2 restart all
```

## Emergency Contacts

**Critical Issues**:
- On-call engineer: [Phone/Slack]
- Database admin: [Phone/Slack]
- DevOps lead: [Phone/Slack]

**External Services**:
- Stripe Support: https://support.stripe.com
- BSC Network Status: https://bscscan.com

## Backup & Disaster Recovery

### Daily Backups

```bash
# Database backup
pg_dump -U neonoble -d neonoble_ramp -F c -f backup_$(date +%Y%m%d).dump

# Upload to S3/backup location
aws s3 cp backup_$(date +%Y%m%d).dump s3://neonoble-backups/
```

### Recovery Time Objectives (RTO)

- **Critical**: < 1 hour (payment processing down)
- **High**: < 4 hours (blockchain transfers down)
- **Medium**: < 24 hours (dev portal unavailable)

### Recovery Point Objectives (RPO)

- **Database**: < 1 hour (continuous replication)
- **Application**: < 5 minutes (last deployment)

## Success Criteria

Launch is successful when:

✅ All validation checks pass
✅ Load test shows >95% success rate
✅ Zero critical bugs in first 24 hours
✅ First 10 transactions complete successfully
✅ Payment webhook delivery 100%
✅ Blockchain transfers confirm within expected time
✅ No stuck sessions after 1 hour
✅ System handles peak load without degradation

---

**Last Updated**: Production Launch
**Version**: 2.0.0
**Owner**: NeoNoble Engineering Team
