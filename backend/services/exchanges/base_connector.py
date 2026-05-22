"""
Base Exchange Connector - Abstract interface for exchange integration.

Defines the common interface for all exchange connectors.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, List, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class OrderSide(str, Enum):
    """Order side."""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type."""
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"


class OrderStatus(str, Enum):
    """Order status."""
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class MarketTicker:
    """Market ticker data."""
    symbol: str
    bid: float
    ask: float
    last: float
    volume_24h: float
    high_24h: float
    low_24h: float
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2
    
    @property
    def spread_pct(self) -> float:
        return ((self.ask - self.bid) / self.mid) * 100 if self.mid > 0 else 0


@dataclass
class ExchangeBalance:
    """Exchange account balance."""
    currency: str
    total: float
    available: float
    locked: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "currency": self.currency,
            "total": self.total,
            "available": self.available,
            "locked": self.locked
        }


@dataclass
class ExchangeOrder:
    """Exchange order."""
    order_id: str
    exchange: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    status: OrderStatus
    quantity: float
    price: Optional[float] = None
    filled_quantity: float = 0.0
    average_price: float = 0.0
    fee: float = 0.0
    fee_currency: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Optional[str] = None
    exchange_order_id: Optional[str] = None
    client_order_id: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "order_id": self.order_id,
            "exchange": self.exchange,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "status": self.status.value,
            "quantity": self.quantity,
            "price": self.price,
            "filled_quantity": self.filled_quantity,
            "average_price": self.average_price,
            "fee": self.fee,
            "fee_currency": self.fee_currency,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "exchange_order_id": self.exchange_order_id,
            "client_order_id": self.client_order_id
        }


class ExchangeConnector(ABC):
    """Abstract base class for exchange connectors."""
    
    def __init__(self, name: str):
        self.name = name
        self._initialized = False
        self._connected = False
        self._api_key: Optional[str] = None
        self._api_secret: Optional[str] = None
    
    @abstractmethod
    async def initialize(self, api_key: str, api_secret: str, **kwargs) -> bool:
        """Initialize the connector with API credentials."""
        pass
    
    @abstractmethod
    async def connect(self) -> bool:
        """Establish connection to the exchange."""
        pass
    
    @abstractmethod
    async def disconnect(self):
        """Disconnect from the exchange."""
        pass
    
    @abstractmethod
    async def get_ticker(self, symbol: str) -> Optional[MarketTicker]:
        """Get current ticker for a symbol."""
        pass
    
    @abstractmethod
    async def get_balances(self) -> List[ExchangeBalance]:
        """Get account balances."""
        pass
    
    @abstractmethod
    async def get_balance(self, currency: str) -> Optional[ExchangeBalance]:
        """Get balance for a specific currency."""
        pass
    
    @abstractmethod
    async def place_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        client_order_id: Optional[str] = None
    ) -> ExchangeOrder:
        """Place a market order."""
        pass
    
    @abstractmethod
    async def place_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        client_order_id: Optional[str] = None
    ) -> ExchangeOrder:
        """Place a limit order."""
        pass
    
    @abstractmethod
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order."""
        pass
    
    @abstractmethod
    async def get_order(self, order_id: str, symbol: str) -> Optional[ExchangeOrder]:
        """Get order status."""
        pass
    
    @abstractmethod
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[ExchangeOrder]:
        """Get all open orders."""
        pass
    
    def is_connected(self) -> bool:
        """Check if connected to exchange."""
        return self._connected
    
    def is_initialized(self) -> bool:
        """Check if initialized with credentials."""
        return self._initialized
