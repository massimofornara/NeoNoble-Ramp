# PostgreSQL Migration Guide

## Overview

This guide describes how to migrate the NeoNoble Ramp platform from MongoDB to PostgreSQL for improved performance, ACID compliance, and enterprise-grade reliability.

## Architecture Changes

### Before (MongoDB)
```
services/*.py → motor.motor_asyncio → MongoDB
```

### After (PostgreSQL)
```
services/*.py → repositories/*.py → SQLAlchemy → PostgreSQL
```

## New Directory Structure

```
/app/backend/
├── database/
│   ├── __init__.py
│   ├── config.py        # Database configuration
│   └── models.py        # SQLAlchemy models
├── repositories/
│   ├── __init__.py
│   ├── base.py          # Repository interfaces
│   └── postgresql.py    # PostgreSQL implementations
└── scripts/
    └── migrate_to_postgresql.py  # Migration script
```

## Database Models

### Users Table
- `id` (PK)
- `email` (unique, indexed)
- `password_hash`
- `role` (user/developer/admin)
- `company_name`
- `created_at`, `updated_at`

### Transactions Table
- `id` (PK)
- `quote_id` (unique, indexed)
- `user_id` (FK → users)
- `direction` (onramp/offramp, indexed)
- `state` (indexed)
- Amounts: `crypto_amount`, `fiat_amount`, `exchange_rate`, `fee_amount`, `net_payout`
- Addresses: `deposit_address`, `wallet_address`
- Payment: `payment_reference`, `payment_amount`, `bank_account`
- Compliance: `kyc_status`, `aml_status`, `por_responsible`
- Timestamps: `expires_at`, `created_at`, `completed_at`
- `metadata` (JSONB)

### Timeline Events Table
- `id` (PK)
- `transaction_id` (FK → transactions)
- `state`
- `message`
- `details` (JSONB)
- `created_at`

### Settlements Table
- `id` (PK)
- `settlement_id` (unique, indexed)
- `transaction_id` (FK → transactions)
- `amount`, `currency`, `status`
- `payout_reference`, `payout_method`
- `metadata` (JSONB)

### Webhooks Table
- `id` (PK)
- `webhook_id` (unique, indexed)
- `api_key_id` (FK → platform_api_keys)
- `url`, `secret`
- `events` (JSONB array)
- `enabled`, `max_retries`, `retry_delays`

### Audit Logs Table
- `id` (PK)
- `event_type` (indexed)
- `quote_id` (indexed)
- `state`, `crypto_amount`, `fiat_amount`
- `details` (JSONB)
- `created_at` (indexed)

## Environment Variables

### PostgreSQL Configuration
```env
DATABASE_TYPE=postgresql
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=neonoble
POSTGRES_PASSWORD=neonoble_secret
POSTGRES_DB=neonoble_ramp
SQL_ECHO=false
```

### MongoDB (Legacy)
```env
DATABASE_TYPE=mongodb
MONGO_URL=mongodb://localhost:27017
DB_NAME=neonoble_ramp
```

## Migration Steps

### 1. Setup PostgreSQL

```bash
# Using Docker
docker run -d \
  --name neonoble-postgres \
  -e POSTGRES_USER=neonoble \
  -e POSTGRES_PASSWORD=neonoble_secret \
  -e POSTGRES_DB=neonoble_ramp \
  -p 5432:5432 \
  postgres:15

# Or install locally
sudo apt install postgresql postgresql-contrib
sudo -u postgres createuser -P neonoble
sudo -u postgres createdb -O neonoble neonoble_ramp
```

### 2. Configure Environment

```bash
# Add to /app/backend/.env
DATABASE_TYPE=postgresql
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=neonoble
POSTGRES_PASSWORD=neonoble_secret
POSTGRES_DB=neonoble_ramp
```

### 3. Run Migration (Dry Run)

```bash
cd /app/backend
python -m scripts.migrate_to_postgresql --dry-run
```

### 4. Execute Migration

```bash
python -m scripts.migrate_to_postgresql --execute
```

### 5. Verify Migration

```bash
# Connect to PostgreSQL
psql -h localhost -U neonoble -d neonoble_ramp

# Check tables
\dt

# Verify counts
SELECT COUNT(*) FROM users;
SELECT COUNT(*) FROM transactions;
SELECT COUNT(*) FROM audit_logs;
```

## Repository Pattern

### Interface (base.py)
```python
class TransactionRepository(BaseRepository):
    async def get_by_quote_id(self, quote_id: str) -> Optional[Transaction]
    async def find_by_state(self, state: str, limit: int = 100) -> List[Transaction]
    async def add_timeline_event(self, quote_id: str, state: str, message: str) -> bool
    async def get_timeline(self, quote_id: str) -> List[TimelineEvent]
```

### PostgreSQL Implementation (postgresql.py)
```python
class PostgresTransactionRepository(TransactionRepository):
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_by_quote_id(self, quote_id: str) -> Optional[Transaction]:
        result = await self.session.execute(
            select(Transaction).where(Transaction.quote_id == quote_id)
        )
        return result.scalar_one_or_none()
```

### Usage in Services
```python
class PoREngine:
    def __init__(self, tx_repo: TransactionRepository):
        self.tx_repo = tx_repo
    
    async def get_transaction(self, quote_id: str):
        return await self.tx_repo.get_by_quote_id(quote_id)
```

## Rollback Plan

If issues occur during migration:

1. **Stop Application**
   ```bash
   sudo supervisorctl stop backend
   ```

2. **Revert to MongoDB**
   ```bash
   # Change .env
   DATABASE_TYPE=mongodb
   ```

3. **Restart Application**
   ```bash
   sudo supervisorctl start backend
   ```

MongoDB data remains intact during migration.

## Performance Considerations

### PostgreSQL Indexes
- `ix_transactions_quote_id` - Quote lookup
- `ix_transactions_state` - State filtering
- `ix_transactions_direction` - On-ramp/Off-ramp queries
- `ix_transactions_created_at` - Recent transactions
- `ix_audit_logs_quote_created` - Audit trail queries

### Connection Pooling
```python
engine = create_async_engine(
    url,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True
)
```

## Testing

After migration, verify:

1. **User Authentication**
   ```bash
   curl -X POST $API_URL/api/auth/login -d '{"email":"test@test.com","password":"test"}'
   ```

2. **Transaction Creation**
   ```bash
   curl -X POST $API_URL/api/ramp/offramp/quote -H "Authorization: Bearer $TOKEN" -d '{"crypto_amount":1,"crypto_currency":"NENO"}'
   ```

3. **Audit Logs**
   ```bash
   curl $API_URL/api/monitoring/audit/events?limit=10
   ```

## Support

For migration issues:
- Check logs: `/var/log/supervisor/backend.err.log`
- Verify PostgreSQL connection: `psql -h $POSTGRES_HOST -U $POSTGRES_USER -d $POSTGRES_DB`
- Review migration script output for errors

---

*Document Version: 1.0.0*  
*Last Updated: January 2025*
