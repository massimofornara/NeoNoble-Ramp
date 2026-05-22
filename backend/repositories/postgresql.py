"""
PostgreSQL Repository Implementations.

Implements all repository interfaces using SQLAlchemy async ORM.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select, update, delete, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.base import (
    UserRepository,
    TransactionRepository,
    ApiKeyRepository,
    SettlementRepository,
    WebhookRepository,
    AuditRepository,
    WalletRepository,
    BlockchainRepository,
    LiquidityRepository
)
from database.models import (
    User, PlatformApiKey, Transaction, TimelineEvent,
    Settlement, Webhook, WebhookDelivery, AuditLog,
    DepositAddress, BlockchainEvent, LiquidityPool
)

logger = logging.getLogger(__name__)


class PostgresUserRepository(UserRepository):
    """PostgreSQL implementation of UserRepository."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, entity: Dict) -> User:
        user = User(**entity)
        self.session.add(user)
        await self.session.flush()
        return user
    
    async def get_by_id(self, id: str) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.id == id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()
    
    async def email_exists(self, email: str) -> bool:
        result = await self.session.execute(
            select(func.count()).select_from(User).where(User.email == email)
        )
        return result.scalar() > 0
    
    async def update(self, id: str, data: Dict[str, Any]) -> Optional[User]:
        await self.session.execute(
            update(User).where(User.id == id).values(**data)
        )
        return await self.get_by_id(id)
    
    async def delete(self, id: str) -> bool:
        result = await self.session.execute(
            delete(User).where(User.id == id)
        )
        return result.rowcount > 0
    
    async def find(
        self,
        filters: Dict[str, Any] = None,
        order_by: str = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[User]:
        query = select(User)
        if filters:
            for key, value in filters.items():
                query = query.where(getattr(User, key) == value)
        if order_by:
            query = query.order_by(getattr(User, order_by))
        query = query.limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())


class PostgresTransactionRepository(TransactionRepository):
    """PostgreSQL implementation of TransactionRepository."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, entity: Dict) -> Transaction:
        # Extract timeline if present
        timeline = entity.pop("timeline", [])
        
        tx = Transaction(**entity)
        self.session.add(tx)
        await self.session.flush()
        
        # Add timeline events
        for event in timeline:
            te = TimelineEvent(
                transaction_id=tx.id,
                state=event.get("state"),
                message=event.get("message"),
                provider=event.get("provider", "internal_por"),
                details=event.get("details", {})
            )
            self.session.add(te)
        
        await self.session.flush()
        return tx
    
    async def get_by_id(self, id: str) -> Optional[Transaction]:
        result = await self.session.execute(
            select(Transaction).where(Transaction.id == id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_quote_id(self, quote_id: str) -> Optional[Transaction]:
        result = await self.session.execute(
            select(Transaction).where(Transaction.quote_id == quote_id)
        )
        return result.scalar_one_or_none()
    
    async def find_by_state(self, state: str, limit: int = 100) -> List[Transaction]:
        result = await self.session.execute(
            select(Transaction)
            .where(Transaction.state == state)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def find_by_user(self, user_id: str, limit: int = 100) -> List[Transaction]:
        result = await self.session.execute(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
    
    async def find_by_direction(
        self,
        direction: str,
        state: str = None,
        limit: int = 100
    ) -> List[Transaction]:
        query = select(Transaction).where(Transaction.direction == direction)
        if state:
            query = query.where(Transaction.state == state)
        query = query.order_by(Transaction.created_at.desc()).limit(limit)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def update(self, id: str, data: Dict[str, Any]) -> Optional[Transaction]:
        # Handle quote_id as identifier
        if "quote_id" in data:
            quote_id = data.pop("quote_id")
            await self.session.execute(
                update(Transaction).where(Transaction.quote_id == quote_id).values(**data)
            )
            return await self.get_by_quote_id(quote_id)
        
        await self.session.execute(
            update(Transaction).where(Transaction.id == id).values(**data)
        )
        return await self.get_by_id(id)
    
    async def delete(self, id: str) -> bool:
        result = await self.session.execute(
            delete(Transaction).where(Transaction.id == id)
        )
        return result.rowcount > 0
    
    async def find(
        self,
        filters: Dict[str, Any] = None,
        order_by: str = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Transaction]:
        query = select(Transaction)
        if filters:
            for key, value in filters.items():
                query = query.where(getattr(Transaction, key) == value)
        if order_by:
            query = query.order_by(getattr(Transaction, order_by).desc())
        else:
            query = query.order_by(Transaction.created_at.desc())
        query = query.limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def add_timeline_event(
        self,
        quote_id: str,
        state: str,
        message: str,
        details: Dict = None,
        provider: str = "internal_por"
    ) -> bool:
        tx = await self.get_by_quote_id(quote_id)
        if not tx:
            return False
        
        event = TimelineEvent(
            transaction_id=tx.id,
            state=state,
            message=message,
            provider=provider,
            details=details or {}
        )
        self.session.add(event)
        await self.session.flush()
        return True
    
    async def get_timeline(self, quote_id: str) -> List[TimelineEvent]:
        tx = await self.get_by_quote_id(quote_id)
        if not tx:
            return []
        
        result = await self.session.execute(
            select(TimelineEvent)
            .where(TimelineEvent.transaction_id == tx.id)
            .order_by(TimelineEvent.created_at)
        )
        return list(result.scalars().all())


class PostgresApiKeyRepository(ApiKeyRepository):
    """PostgreSQL implementation of ApiKeyRepository."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, entity: Dict) -> PlatformApiKey:
        key = PlatformApiKey(**entity)
        self.session.add(key)
        await self.session.flush()
        return key
    
    async def get_by_id(self, id: str) -> Optional[PlatformApiKey]:
        result = await self.session.execute(
            select(PlatformApiKey).where(PlatformApiKey.id == id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_api_key(self, api_key: str) -> Optional[PlatformApiKey]:
        result = await self.session.execute(
            select(PlatformApiKey).where(PlatformApiKey.api_key == api_key)
        )
        return result.scalar_one_or_none()
    
    async def find_by_user(self, user_id: str) -> List[PlatformApiKey]:
        result = await self.session.execute(
            select(PlatformApiKey)
            .where(PlatformApiKey.user_id == user_id)
            .order_by(PlatformApiKey.created_at.desc())
        )
        return list(result.scalars().all())
    
    async def revoke(self, api_key: str) -> bool:
        result = await self.session.execute(
            update(PlatformApiKey)
            .where(PlatformApiKey.api_key == api_key)
            .values(status="revoked")
        )
        return result.rowcount > 0
    
    async def update(self, id: str, data: Dict[str, Any]) -> Optional[PlatformApiKey]:
        await self.session.execute(
            update(PlatformApiKey).where(PlatformApiKey.id == id).values(**data)
        )
        return await self.get_by_id(id)
    
    async def delete(self, id: str) -> bool:
        result = await self.session.execute(
            delete(PlatformApiKey).where(PlatformApiKey.id == id)
        )
        return result.rowcount > 0
    
    async def find(
        self,
        filters: Dict[str, Any] = None,
        order_by: str = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[PlatformApiKey]:
        query = select(PlatformApiKey)
        if filters:
            for key, value in filters.items():
                query = query.where(getattr(PlatformApiKey, key) == value)
        query = query.limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())


class PostgresAuditRepository(AuditRepository):
    """PostgreSQL implementation of AuditRepository."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, entity: Dict) -> AuditLog:
        log = AuditLog(**entity)
        self.session.add(log)
        await self.session.flush()
        return log
    
    async def get_by_id(self, id: str) -> Optional[AuditLog]:
        result = await self.session.execute(
            select(AuditLog).where(AuditLog.id == id)
        )
        return result.scalar_one_or_none()
    
    async def log_event(
        self,
        event_type: str,
        quote_id: str = None,
        settlement_id: str = None,
        state: str = None,
        crypto_amount: float = None,
        crypto_currency: str = None,
        fiat_amount: float = None,
        details: Dict = None
    ) -> AuditLog:
        log = AuditLog(
            event_type=event_type,
            quote_id=quote_id,
            settlement_id=settlement_id,
            state=state,
            crypto_amount=crypto_amount,
            crypto_currency=crypto_currency,
            fiat_amount=fiat_amount,
            details=details or {}
        )
        self.session.add(log)
        await self.session.flush()
        return log
    
    async def get_trail(self, quote_id: str) -> List[AuditLog]:
        result = await self.session.execute(
            select(AuditLog)
            .where(AuditLog.quote_id == quote_id)
            .order_by(AuditLog.created_at)
        )
        return list(result.scalars().all())
    
    async def get_recent(self, event_type: str = None, limit: int = 100) -> List[AuditLog]:
        query = select(AuditLog)
        if event_type:
            query = query.where(AuditLog.event_type == event_type)
        query = query.order_by(AuditLog.created_at.desc()).limit(limit)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def update(self, id: str, data: Dict[str, Any]) -> Optional[AuditLog]:
        await self.session.execute(
            update(AuditLog).where(AuditLog.id == id).values(**data)
        )
        return await self.get_by_id(id)
    
    async def delete(self, id: str) -> bool:
        result = await self.session.execute(
            delete(AuditLog).where(AuditLog.id == id)
        )
        return result.rowcount > 0
    
    async def find(
        self,
        filters: Dict[str, Any] = None,
        order_by: str = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[AuditLog]:
        query = select(AuditLog)
        if filters:
            for key, value in filters.items():
                query = query.where(getattr(AuditLog, key) == value)
        query = query.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())


class PostgresWebhookRepository(WebhookRepository):
    """PostgreSQL implementation of WebhookRepository."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create(self, entity: Dict) -> Webhook:
        webhook = Webhook(**entity)
        self.session.add(webhook)
        await self.session.flush()
        return webhook
    
    async def get_by_id(self, id: str) -> Optional[Webhook]:
        result = await self.session.execute(
            select(Webhook).where(Webhook.id == id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_webhook_id(self, webhook_id: str) -> Optional[Webhook]:
        result = await self.session.execute(
            select(Webhook).where(Webhook.webhook_id == webhook_id)
        )
        return result.scalar_one_or_none()
    
    async def find_by_api_key(self, api_key_id: str) -> List[Webhook]:
        result = await self.session.execute(
            select(Webhook).where(Webhook.api_key_id == api_key_id)
        )
        return list(result.scalars().all())
    
    async def find_enabled(self) -> List[Webhook]:
        result = await self.session.execute(
            select(Webhook).where(Webhook.enabled.is_(True))
        )
        return list(result.scalars().all())
    
    async def create_delivery(self, delivery: Dict) -> WebhookDelivery:
        dlv = WebhookDelivery(**delivery)
        self.session.add(dlv)
        await self.session.flush()
        return dlv
    
    async def update_delivery(self, delivery_id: str, data: Dict) -> bool:
        result = await self.session.execute(
            update(WebhookDelivery)
            .where(WebhookDelivery.delivery_id == delivery_id)
            .values(**data)
        )
        return result.rowcount > 0
    
    async def get_deliveries(
        self,
        webhook_id: str = None,
        event_id: str = None,
        status: str = None,
        limit: int = 50
    ) -> List[WebhookDelivery]:
        query = select(WebhookDelivery)
        if webhook_id:
            query = query.where(WebhookDelivery.webhook_id == webhook_id)
        if event_id:
            query = query.where(WebhookDelivery.event_id == event_id)
        if status:
            query = query.where(WebhookDelivery.status == status)
        query = query.order_by(WebhookDelivery.created_at.desc()).limit(limit)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def update(self, id: str, data: Dict[str, Any]) -> Optional[Webhook]:
        await self.session.execute(
            update(Webhook).where(Webhook.id == id).values(**data)
        )
        return await self.get_by_id(id)
    
    async def delete(self, id: str) -> bool:
        result = await self.session.execute(
            delete(Webhook).where(Webhook.id == id)
        )
        return result.rowcount > 0
    
    async def find(
        self,
        filters: Dict[str, Any] = None,
        order_by: str = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Webhook]:
        query = select(Webhook)
        if filters:
            for key, value in filters.items():
                query = query.where(getattr(Webhook, key) == value)
        query = query.limit(limit).offset(offset)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
