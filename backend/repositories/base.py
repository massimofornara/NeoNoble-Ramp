"""
Repository Base Classes and Interfaces.

Provides abstract base classes for database operations,
enabling database-agnostic service layer.
"""

from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Optional, List, Dict, Any
from datetime import datetime

T = TypeVar('T')


class BaseRepository(ABC, Generic[T]):
    """
    Abstract base repository defining common CRUD operations.
    
    All concrete repositories should implement these methods
    for both PostgreSQL and MongoDB backends.
    """
    
    @abstractmethod
    async def create(self, entity: T) -> T:
        """Create a new entity."""
        pass
    
    @abstractmethod
    async def get_by_id(self, id: str) -> Optional[T]:
        """Get entity by primary ID."""
        pass
    
    @abstractmethod
    async def update(self, id: str, data: Dict[str, Any]) -> Optional[T]:
        """Update entity by ID."""
        pass
    
    @abstractmethod
    async def delete(self, id: str) -> bool:
        """Delete entity by ID."""
        pass
    
    @abstractmethod
    async def find(
        self,
        filters: Dict[str, Any] = None,
        order_by: str = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[T]:
        """Find entities matching filters."""
        pass


class UserRepository(BaseRepository):
    """User repository interface."""
    
    @abstractmethod
    async def get_by_email(self, email: str) -> Optional[Any]:
        """Get user by email."""
        pass
    
    @abstractmethod
    async def email_exists(self, email: str) -> bool:
        """Check if email exists."""
        pass


class TransactionRepository(BaseRepository):
    """Transaction repository interface."""
    
    @abstractmethod
    async def get_by_quote_id(self, quote_id: str) -> Optional[Any]:
        """Get transaction by quote ID."""
        pass
    
    @abstractmethod
    async def find_by_state(self, state: str, limit: int = 100) -> List[Any]:
        """Find transactions by state."""
        pass
    
    @abstractmethod
    async def find_by_user(self, user_id: str, limit: int = 100) -> List[Any]:
        """Find transactions by user."""
        pass
    
    @abstractmethod
    async def find_by_direction(self, direction: str, state: str = None, limit: int = 100) -> List[Any]:
        """Find transactions by direction (onramp/offramp)."""
        pass
    
    @abstractmethod
    async def add_timeline_event(
        self,
        quote_id: str,
        state: str,
        message: str,
        details: Dict = None,
        provider: str = "internal_por"
    ) -> bool:
        """Add timeline event to transaction."""
        pass
    
    @abstractmethod
    async def get_timeline(self, quote_id: str) -> List[Any]:
        """Get transaction timeline."""
        pass


class ApiKeyRepository(BaseRepository):
    """API Key repository interface."""
    
    @abstractmethod
    async def get_by_api_key(self, api_key: str) -> Optional[Any]:
        """Get by API key string."""
        pass
    
    @abstractmethod
    async def find_by_user(self, user_id: str) -> List[Any]:
        """Find all keys for a user."""
        pass
    
    @abstractmethod
    async def revoke(self, api_key: str) -> bool:
        """Revoke an API key."""
        pass


class SettlementRepository(BaseRepository):
    """Settlement repository interface."""
    
    @abstractmethod
    async def get_by_settlement_id(self, settlement_id: str) -> Optional[Any]:
        """Get by settlement ID."""
        pass
    
    @abstractmethod
    async def find_by_transaction(self, transaction_id: str) -> Optional[Any]:
        """Find settlement for a transaction."""
        pass
    
    @abstractmethod
    async def get_statistics(self) -> Dict[str, Any]:
        """Get settlement statistics."""
        pass


class WebhookRepository(BaseRepository):
    """Webhook repository interface."""
    
    @abstractmethod
    async def get_by_webhook_id(self, webhook_id: str) -> Optional[Any]:
        """Get by webhook ID."""
        pass
    
    @abstractmethod
    async def find_by_api_key(self, api_key_id: str) -> List[Any]:
        """Find webhooks for an API key."""
        pass
    
    @abstractmethod
    async def find_enabled(self) -> List[Any]:
        """Find all enabled webhooks."""
        pass
    
    @abstractmethod
    async def create_delivery(self, delivery: Dict) -> Any:
        """Create webhook delivery record."""
        pass
    
    @abstractmethod
    async def update_delivery(self, delivery_id: str, data: Dict) -> bool:
        """Update webhook delivery status."""
        pass
    
    @abstractmethod
    async def get_deliveries(
        self,
        webhook_id: str = None,
        event_id: str = None,
        status: str = None,
        limit: int = 50
    ) -> List[Any]:
        """Get webhook deliveries."""
        pass


class AuditRepository(BaseRepository):
    """Audit log repository interface."""
    
    @abstractmethod
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
    ) -> Any:
        """Log an audit event."""
        pass
    
    @abstractmethod
    async def get_trail(self, quote_id: str) -> List[Any]:
        """Get audit trail for a quote."""
        pass
    
    @abstractmethod
    async def get_recent(self, event_type: str = None, limit: int = 100) -> List[Any]:
        """Get recent audit events."""
        pass


class WalletRepository(BaseRepository):
    """Wallet/deposit address repository interface."""
    
    @abstractmethod
    async def get_by_address(self, address: str) -> Optional[Any]:
        """Get by address."""
        pass
    
    @abstractmethod
    async def get_by_quote_id(self, quote_id: str) -> Optional[Any]:
        """Get address for a quote."""
        pass
    
    @abstractmethod
    async def mark_used(self, address: str) -> bool:
        """Mark address as used."""
        pass


class BlockchainRepository(BaseRepository):
    """Blockchain event repository interface."""
    
    @abstractmethod
    async def get_by_tx_hash(self, tx_hash: str) -> Optional[Any]:
        """Get by transaction hash."""
        pass
    
    @abstractmethod
    async def find_by_address(self, address: str, status: str = None) -> List[Any]:
        """Find events for an address."""
        pass
    
    @abstractmethod
    async def mark_processed(self, tx_hash: str) -> bool:
        """Mark event as processed."""
        pass


class LiquidityRepository(BaseRepository):
    """Liquidity pool repository interface."""
    
    @abstractmethod
    async def get_pool(self, pool_name: str = "default") -> Optional[Any]:
        """Get liquidity pool status."""
        pass
    
    @abstractmethod
    async def reserve(self, pool_name: str, amount: float) -> bool:
        """Reserve liquidity."""
        pass
    
    @abstractmethod
    async def release(self, pool_name: str, amount: float) -> bool:
        """Release reserved liquidity."""
        pass
