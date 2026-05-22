"""
Database Migration Script.

Migrates data from MongoDB to PostgreSQL while maintaining
backward compatibility.

Usage:
    python -m scripts.migrate_to_postgresql --dry-run
    python -m scripts.migrate_to_postgresql --execute
"""

import asyncio
import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text

from database.config import Base
from database.models import (
    User, PlatformApiKey, Transaction, TimelineEvent,
    Settlement, Webhook, WebhookDelivery, AuditLog,
    DepositAddress, BlockchainEvent, LiquidityPool
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DatabaseMigrator:
    """Handles migration from MongoDB to PostgreSQL."""
    
    def __init__(self, dry_run: bool = True):
        self.dry_run = dry_run
        
        # MongoDB connection
        self.mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        self.mongo_db_name = os.environ.get("DB_NAME", "neonoble_ramp")
        self.mongo_client = None
        self.mongo_db = None
        
        # PostgreSQL connection
        pg_host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
        pg_port = os.environ.get("POSTGRES_PORT", "5432")
        pg_user = os.environ.get("POSTGRES_USER", "neonoble")
        pg_password = os.environ.get("POSTGRES_PASSWORD", "neonoble_secret_2025")
        pg_database = os.environ.get("POSTGRES_DB", "neonoble_ramp")
        
        self.pg_url = f"postgresql+asyncpg://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"
        self.pg_engine = None
        self.pg_session_factory = None
        
        # Migration statistics
        self.stats = {
            "users": {"migrated": 0, "skipped": 0, "errors": 0},
            "api_keys": {"migrated": 0, "skipped": 0, "errors": 0},
            "transactions": {"migrated": 0, "skipped": 0, "errors": 0},
            "settlements": {"migrated": 0, "skipped": 0, "errors": 0},
            "webhooks": {"migrated": 0, "skipped": 0, "errors": 0},
            "audit_logs": {"migrated": 0, "skipped": 0, "errors": 0},
            "deposit_addresses": {"migrated": 0, "skipped": 0, "errors": 0},
            "blockchain_events": {"migrated": 0, "skipped": 0, "errors": 0}
        }
    
    async def connect(self):
        """Establish database connections."""
        logger.info("Connecting to databases...")
        
        # MongoDB
        self.mongo_client = AsyncIOMotorClient(self.mongo_url)
        self.mongo_db = self.mongo_client[self.mongo_db_name]
        logger.info(f"Connected to MongoDB: {self.mongo_db_name}")
        
        # PostgreSQL
        self.pg_engine = create_async_engine(self.pg_url, echo=False)
        self.pg_session_factory = async_sessionmaker(
            self.pg_engine, class_=AsyncSession, expire_on_commit=False
        )
        
        # Create tables
        async with self.pg_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("Connected to PostgreSQL and created tables")
    
    async def disconnect(self):
        """Close database connections."""
        if self.mongo_client:
            self.mongo_client.close()
        if self.pg_engine:
            await self.pg_engine.dispose()
    
    def _parse_datetime(self, value, default_now: bool = True) -> Optional[datetime]:
        """
        Parse datetime from various MongoDB formats to timezone-aware Python datetime.
        
        Handles:
        - None values
        - Python datetime objects (makes timezone-aware if naive)
        - ISO 8601 strings with 'Z' suffix (e.g., '2026-01-06T17:21:05.187Z')
        - ISO 8601 strings with timezone offset
        - Fallback to current UTC time if parsing fails
        
        Args:
            value: The datetime value to parse (None, datetime, or string)
            default_now: If True, return current UTC time on parse failure; if False, return None
            
        Returns:
            Timezone-aware datetime object (UTC normalized) or None
        """
        if value is None:
            return datetime.now(timezone.utc) if default_now else None
            
        if isinstance(value, datetime):
            # Ensure timezone awareness - normalize to UTC
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
            
        if isinstance(value, str):
            try:
                # Handle ISO 8601 with 'Z' (Zulu time) suffix
                if value.endswith('Z'):
                    return datetime.fromisoformat(value.replace('Z', '+00:00'))
                # Handle ISO 8601 with explicit timezone
                return datetime.fromisoformat(value)
            except ValueError:
                logger.warning(f"Failed to parse datetime string: {value}")
                return datetime.now(timezone.utc) if default_now else None
                
        # For any other type, log and use default
        logger.warning(f"Unexpected datetime type: {type(value)} - {value}")
        return datetime.now(timezone.utc) if default_now else None
    
    async def migrate_users(self):
        """Migrate users collection."""
        logger.info("Migrating users...")
        
        async with self.pg_session_factory() as session:
            cursor = self.mongo_db.users.find({})
            async for doc in cursor:
                try:
                    user = User(
                        id=doc.get("id", str(doc.get("_id"))),
                        email=doc.get("email"),
                        password_hash=doc.get("password_hash"),
                        role=doc.get("role", "user"),
                        company_name=doc.get("company_name"),
                        created_at=self._parse_datetime(doc.get("created_at"))
                    )
                    
                    if not self.dry_run:
                        session.add(user)
                        await session.commit()
                    
                    self.stats["users"]["migrated"] += 1
                    
                except Exception as e:
                    logger.error(f"Error migrating user {doc.get('email')}: {e}")
                    self.stats["users"]["errors"] += 1
                    if not self.dry_run:
                        await session.rollback()
        
        logger.info(f"Users: {self.stats['users']}")
    
    async def migrate_api_keys(self):
        """Migrate platform_api_keys collection."""
        logger.info("Migrating API keys...")
        
        async with self.pg_session_factory() as session:
            cursor = self.mongo_db.platform_api_keys.find({})
            async for doc in cursor:
                try:
                    # Handle missing encrypted_api_secret - use placeholder for legacy keys
                    encrypted_secret = doc.get("encrypted_api_secret")
                    if not encrypted_secret:
                        encrypted_secret = "LEGACY_KEY_NO_SECRET_STORED"
                        logger.warning(f"API key {doc.get('api_key')} has no secret - using placeholder")
                    
                    api_key = PlatformApiKey(
                        id=doc.get("id", str(doc.get("_id"))),
                        user_id=doc.get("user_id"),
                        name=doc.get("name", "Migrated Key"),
                        api_key=doc.get("api_key"),
                        encrypted_api_secret=encrypted_secret,
                        status=doc.get("status", "active"),
                        created_at=self._parse_datetime(doc.get("created_at")),
                        last_used_at=self._parse_datetime(doc.get("last_used_at"), default_now=False)
                    )
                    
                    if not self.dry_run:
                        session.add(api_key)
                        await session.commit()
                    
                    self.stats["api_keys"]["migrated"] += 1
                    
                except Exception as e:
                    logger.error(f"Error migrating API key {doc.get('api_key')}: {e}")
                    self.stats["api_keys"]["errors"] += 1
                    if not self.dry_run:
                        await session.rollback()
        
        logger.info(f"API Keys: {self.stats['api_keys']}")
    
    async def migrate_transactions(self):
        """Migrate por_transactions collection."""
        logger.info("Migrating transactions...")
        
        async with self.pg_session_factory() as session:
            cursor = self.mongo_db.por_transactions.find({})
            async for doc in cursor:
                try:
                    # Parse compliance data
                    compliance = doc.get("compliance", {})
                    
                    tx = Transaction(
                        id=doc.get("id", str(doc.get("_id"))),
                        quote_id=doc.get("quote_id"),
                        user_id=doc.get("metadata", {}).get("user_id"),
                        direction=doc.get("direction", "offramp"),
                        provider=doc.get("provider", "internal_por"),
                        crypto_amount=doc.get("crypto_amount"),
                        crypto_currency=doc.get("crypto_currency"),
                        fiat_amount=doc.get("fiat_amount"),
                        fiat_currency=doc.get("fiat_currency", "EUR"),
                        exchange_rate=doc.get("exchange_rate"),
                        fee_amount=doc.get("fee_amount"),
                        fee_percentage=doc.get("fee_percentage", 1.5),
                        net_payout=doc.get("net_payout"),
                        deposit_address=doc.get("deposit_address"),
                        wallet_address=doc.get("wallet_address"),
                        payment_reference=doc.get("payment_reference"),
                        payment_amount=doc.get("payment_amount"),
                        bank_account=doc.get("metadata", {}).get("bank_account"),
                        state=doc.get("state"),
                        kyc_status=compliance.get("kyc_status", "not_required"),
                        kyc_provider=compliance.get("kyc_provider", "internal_por"),
                        kyc_verified_at=self._parse_datetime(compliance.get("kyc_verified_at"), default_now=False),
                        aml_status=compliance.get("aml_status", "not_required"),
                        aml_provider=compliance.get("aml_provider", "internal_por"),
                        aml_cleared_at=self._parse_datetime(compliance.get("aml_cleared_at"), default_now=False),
                        risk_score=compliance.get("risk_score"),
                        risk_level=compliance.get("risk_level", "low"),
                        por_responsible=compliance.get("por_responsible", True),
                        expires_at=self._parse_datetime(doc.get("expires_at")),
                        created_at=self._parse_datetime(doc.get("created_at")),
                        completed_at=self._parse_datetime(doc.get("completed_at"), default_now=False),
                        extra_data=doc.get("metadata", {})
                    )
                    
                    if not self.dry_run:
                        session.add(tx)
                        await session.flush()
                        
                        # Migrate timeline events
                        for event in doc.get("timeline", []):
                            te = TimelineEvent(
                                transaction_id=tx.id,
                                state=event.get("state"),
                                message=event.get("message"),
                                provider=event.get("provider", "internal_por"),
                                details=event.get("details", {}),
                                created_at=self._parse_datetime(event.get("timestamp"))
                            )
                            session.add(te)
                        
                        await session.commit()
                    
                    self.stats["transactions"]["migrated"] += 1
                    
                except Exception as e:
                    logger.error(f"Error migrating transaction {doc.get('quote_id')}: {e}")
                    self.stats["transactions"]["errors"] += 1
                    if not self.dry_run:
                        await session.rollback()
        
        logger.info(f"Transactions: {self.stats['transactions']}")
    
    async def migrate_settlements(self):
        """Migrate por_settlements collection."""
        logger.info("Migrating settlements...")
        
        async with self.pg_session_factory() as session:
            cursor = self.mongo_db.por_settlements.find({})
            async for doc in cursor:
                try:
                    # Handle field name differences between MongoDB and PostgreSQL models
                    # MongoDB uses amount_eur, model uses amount
                    amount = doc.get("amount") or doc.get("amount_eur")
                    if amount is None:
                        logger.warning(f"Settlement {doc.get('settlement_id')} has no amount - skipping")
                        self.stats["settlements"]["skipped"] += 1
                        continue
                    
                    # Get transaction_id from quote_id lookup if not directly available
                    transaction_id = doc.get("transaction_id")
                    if not transaction_id and doc.get("quote_id"):
                        # Try to find transaction by quote_id
                        tx = await self.mongo_db.por_transactions.find_one({"quote_id": doc.get("quote_id")})
                        if tx:
                            transaction_id = tx.get("id", str(tx.get("_id")))
                    
                    settlement = Settlement(
                        id=doc.get("id", str(doc.get("_id"))),
                        settlement_id=doc.get("settlement_id"),
                        transaction_id=transaction_id,
                        amount=amount,
                        currency=doc.get("currency", "EUR"),
                        status=doc.get("status"),
                        payout_reference=doc.get("payout_reference"),
                        payout_method=doc.get("payout_method") or doc.get("settlement_mode", "internal_por"),
                        created_at=self._parse_datetime(doc.get("created_at")),
                        completed_at=self._parse_datetime(doc.get("completed_at"), default_now=False),
                        extra_data=doc.get("metadata", {})
                    )
                    
                    if not self.dry_run:
                        session.add(settlement)
                        await session.commit()
                    
                    self.stats["settlements"]["migrated"] += 1
                    
                except Exception as e:
                    logger.error(f"Error migrating settlement {doc.get('settlement_id')}: {e}")
                    self.stats["settlements"]["errors"] += 1
                    if not self.dry_run:
                        await session.rollback()
        
        logger.info(f"Settlements: {self.stats['settlements']}")
    
    async def migrate_webhooks(self):
        """Migrate webhooks collection."""
        logger.info("Migrating webhooks...")
        
        async with self.pg_session_factory() as session:
            cursor = self.mongo_db.webhooks.find({})
            async for doc in cursor:
                try:
                    webhook = Webhook(
                        id=doc.get("id", str(doc.get("_id"))),
                        webhook_id=doc.get("webhook_id"),
                        api_key_id=doc.get("api_key_id"),
                        url=doc.get("url"),
                        secret=doc.get("secret"),
                        events=doc.get("events", []),
                        enabled=doc.get("enabled", True),
                        max_retries=doc.get("max_retries", 5),
                        retry_delays=doc.get("retry_delays", [30, 60, 300, 900, 3600]),
                        created_at=self._parse_datetime(doc.get("created_at"))
                    )
                    
                    if not self.dry_run:
                        session.add(webhook)
                        await session.commit()
                    
                    self.stats["webhooks"]["migrated"] += 1
                    
                except Exception as e:
                    logger.error(f"Error migrating webhook {doc.get('webhook_id')}: {e}")
                    self.stats["webhooks"]["errors"] += 1
                    if not self.dry_run:
                        await session.rollback()
        
        logger.info(f"Webhooks: {self.stats['webhooks']}")
    
    async def migrate_audit_logs(self):
        """Migrate audit_logs collection."""
        logger.info("Migrating audit logs...")
        
        async with self.pg_session_factory() as session:
            cursor = self.mongo_db.audit_logs.find({})
            async for doc in cursor:
                try:
                    audit = AuditLog(
                        id=str(doc.get("_id")),
                        event_type=doc.get("event_type"),
                        quote_id=doc.get("quote_id"),
                        settlement_id=doc.get("settlement_id"),
                        state=doc.get("state"),
                        crypto_amount=doc.get("crypto_amount"),
                        crypto_currency=doc.get("crypto_currency"),
                        fiat_amount=doc.get("fiat_amount"),
                        extra_details=doc.get("details", {}),
                        created_at=self._parse_datetime(doc.get("timestamp"))
                    )
                    
                    if not self.dry_run:
                        session.add(audit)
                        await session.commit()
                    
                    self.stats["audit_logs"]["migrated"] += 1
                    
                except Exception as e:
                    logger.error(f"Error migrating audit log: {e}")
                    self.stats["audit_logs"]["errors"] += 1
                    if not self.dry_run:
                        await session.rollback()
        
        logger.info(f"Audit Logs: {self.stats['audit_logs']}")
    
    async def run_migration(self):
        """Run the full migration."""
        logger.info("=" * 60)
        logger.info(f"Starting migration {'(DRY RUN)' if self.dry_run else '(EXECUTING)'}")
        logger.info("=" * 60)
        
        await self.connect()
        
        try:
            await self.migrate_users()
            await self.migrate_api_keys()
            await self.migrate_transactions()
            await self.migrate_settlements()
            await self.migrate_webhooks()
            await self.migrate_audit_logs()
            
        finally:
            await self.disconnect()
        
        logger.info("=" * 60)
        logger.info("Migration Summary:")
        for collection, stats in self.stats.items():
            logger.info(f"  {collection}: {stats}")
        logger.info("=" * 60)
        
        if self.dry_run:
            logger.info("This was a DRY RUN. Use --execute to perform actual migration.")


async def main():
    parser = argparse.ArgumentParser(description="Migrate MongoDB to PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", default=True,
                       help="Perform dry run without actually migrating")
    parser.add_argument("--execute", action="store_true",
                       help="Execute the migration")
    
    args = parser.parse_args()
    
    dry_run = not args.execute
    
    migrator = DatabaseMigrator(dry_run=dry_run)
    await migrator.run_migration()


if __name__ == "__main__":
    asyncio.run(main())
