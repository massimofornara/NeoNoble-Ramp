"""
Exchange Connectors Package - Live Venue Integration.

Provides real exchange connectivity for:
- Market data (prices, order books)
- Order execution (spot trading)
- Account management (balances, positions)

Supported Exchanges:
- Binance (primary)
- Kraken (fallback)
- Coinbase (additional venue)
- NENO Virtual Exchange (platform-managed)
"""

from .base_connector import (
    ExchangeConnector,
    OrderSide,
    OrderType,
    OrderStatus,
    ExchangeOrder,
    ExchangeBalance,
    MarketTicker
)

from .binance_connector import BinanceConnector
from .kraken_connector import KrakenConnector
from .coinbase_connector import CoinbaseConnector
from .neno_virtual_exchange import NenoVirtualExchange, get_neno_exchange
from .connector_manager import ConnectorManager, get_connector_manager, set_connector_manager

__all__ = [
    'ExchangeConnector',
    'OrderSide',
    'OrderType',
    'OrderStatus',
    'ExchangeOrder',
    'ExchangeBalance',
    'MarketTicker',
    'BinanceConnector',
    'KrakenConnector',
    'CoinbaseConnector',
    'NenoVirtualExchange',
    'get_neno_exchange',
    'ConnectorManager',
    'get_connector_manager',
    'set_connector_manager'
]
