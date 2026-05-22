"""
Binance Connector - Live trading integration with Binance.

Supports:
- Spot trading (market and limit orders)
- Account balances
- Market data (tickers, order books)

Symbol format: BTCUSDT, ETHUSDT, BNBUSDT, etc.
"""

import os
import logging
import hmac
import hashlib
import time
import aiohttp

from typing import Optional, Dict, List
from datetime import datetime, timezone
from uuid import uuid4

from .base_connector import (
    ExchangeConnector,
    OrderSide,
    OrderType,
    OrderStatus,
    ExchangeOrder,
    ExchangeBalance,
    MarketTicker
)

from binance.client import Client

class BinanceConnector:

    def __init__(self):
        self.client = Client(
            os.getenv("BINANCE_API_KEY"),
            os.getenv("BINANCE_API_SECRET")
        )

    async def place_market_order(self, symbol, side, quantity):
        order = self.client.create_order(
            symbol=symbol,
            side=side.upper(),
            type="MARKET",
            quantity=quantity
        )

        return type("Order", (), {
            "order_id": order["orderId"],
            "average_price": float(order["fills"][0]["price"]),
            "filled_quantity": float(order["executedQty"])
        }), None

    async def get_ticker(self, symbol):
        ticker = self.client.get_symbol_ticker(symbol=symbol)
        return type("Ticker", (), {
            "last": float(ticker["price"])
        }), "binance"


logger = logging.getLogger(__name__)

# Binance API endpoints
BINANCE_API_URL = "https://api.binance.com"
BINANCE_TESTNET_URL = "https://testnet.binance.vision"


class BinanceConnector(ExchangeConnector):
    """
    Binance exchange connector for live trading.
    
    Features:
    - Spot market and limit orders
    - Real-time balances
    - Market data access
    - HMAC-SHA256 authentication
    """
    
    def __init__(self, testnet: bool = False):
        super().__init__("binance")
        self._testnet = testnet
        self._base_url = BINANCE_TESTNET_URL if testnet else BINANCE_API_URL
        self._recv_window = 5000
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self, api_key: str, api_secret: str, **kwargs) -> bool:
        """Initialize with Binance API credentials."""
        try:
            self._api_key = api_key
            self._api_secret = api_secret
            self._testnet = kwargs.get("testnet", self._testnet)
            self._base_url = BINANCE_TESTNET_URL if self._testnet else BINANCE_API_URL
            
            self._initialized = True
            logger.info(f"[BINANCE] Initialized ({'testnet' if self._testnet else 'mainnet'})")
            return True
        except Exception as e:
            logger.error(f"[BINANCE] Initialization failed: {e}")
            return False
    
    async def connect(self) -> bool:
        """Connect to Binance API."""
        try:
            if self._session is None:
                self._session = aiohttp.ClientSession()
            
            # Test connection with server time
            async with self._session.get(f"{self._base_url}/api/v3/time") as response:
                if response.status == 200:
                    self._connected = True
                    logger.info("[BINANCE] Connected successfully")
                    return True
                else:
                    logger.error(f"[BINANCE] Connection failed: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"[BINANCE] Connection error: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from Binance."""
        if self._session:
            await self._session.close()
            self._session = None
        self._connected = False
        logger.info("[BINANCE] Disconnected")
    
    def _generate_signature(self, params: Dict) -> str:
        """Generate HMAC-SHA256 signature for authenticated requests."""
        query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        signature = hmac.new(
            self._api_secret.encode(),
            query_string.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def _get_timestamp(self) -> int:
        """Get current timestamp in milliseconds."""
        return int(time.time() * 1000)
    
    async def _signed_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None
    ) -> Dict:
        """Make a signed API request."""
        if not self._session:
            self._session = aiohttp.ClientSession()
        
        params = params or {}
        params["timestamp"] = self._get_timestamp()
        params["recvWindow"] = self._recv_window
        params["signature"] = self._generate_signature(params)
        
        headers = {"X-MBX-APIKEY": self._api_key}
        url = f"{self._base_url}{endpoint}"
        
        if method == "GET":
            async with self._session.get(url, params=params, headers=headers) as response:
                return await response.json()
        elif method == "POST":
            async with self._session.post(url, params=params, headers=headers) as response:
                return await response.json()
        elif method == "DELETE":
            async with self._session.delete(url, params=params, headers=headers) as response:
                return await response.json()
        
        return {}
    
    async def _public_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make a public API request (no authentication)."""
        if not self._session:
            self._session = aiohttp.ClientSession()
        
        url = f"{self._base_url}{endpoint}"
        async with self._session.get(url, params=params) as response:
            return await response.json()
    
    async def get_ticker(self, symbol: str) -> Optional[MarketTicker]:
        """Get current ticker for a symbol."""
        # Handle NENO symbols with virtual pricing
        if self._is_neno_symbol(symbol):
            return self._get_neno_ticker(symbol)
        
        try:
            data = await self._public_request("/api/v3/ticker/24hr", {"symbol": symbol})
            
            if "code" in data:
                logger.error(f"[BINANCE] Ticker error: {data}")
                return None
            
            return MarketTicker(
                symbol=symbol,
                bid=float(data.get("bidPrice", 0)),
                ask=float(data.get("askPrice", 0)),
                last=float(data.get("lastPrice", 0)),
                volume_24h=float(data.get("volume", 0)),
                high_24h=float(data.get("highPrice", 0)),
                low_24h=float(data.get("lowPrice", 0))
            )
        except Exception as e:
            logger.error(f"[BINANCE] Ticker error for {symbol}: {e}")
            return None
    
    def _is_neno_symbol(self, symbol: str) -> bool:
        """Check if symbol is NENO."""
        return 'NENO' in symbol.upper()
    
    def _get_neno_ticker(self, symbol: str) -> MarketTicker:
        """Get NENO ticker with fixed price."""
        from .neno_mixin import get_neno_ticker_data
        data = get_neno_ticker_data(symbol)
        return MarketTicker(
            symbol=data['symbol'],
            bid=data['bid'],
            ask=data['ask'],
            last=data['last'],
            volume_24h=data['volume_24h'],
            high_24h=data['high_24h'],
            low_24h=data['low_24h']
        )
    
    async def get_balances(self) -> List[ExchangeBalance]:
        """Get all account balances."""
        try:
            data = await self._signed_request("GET", "/api/v3/account")
            
            if "code" in data:
                logger.error(f"[BINANCE] Balance error: {data}")
                return []
            
            balances = []
            for asset in data.get("balances", []):
                free = float(asset.get("free", 0))
                locked = float(asset.get("locked", 0))
                if free > 0 or locked > 0:
                    balances.append(ExchangeBalance(
                        currency=asset["asset"],
                        total=free + locked,
                        available=free,
                        locked=locked
                    ))
            
            return balances
        except Exception as e:
            logger.error(f"[BINANCE] Balance error: {e}")
            return []
    
    async def get_balance(self, currency: str) -> Optional[ExchangeBalance]:
        """Get balance for a specific currency."""
        balances = await self.get_balances()
        for balance in balances:
            if balance.currency == currency:
                return balance
        return ExchangeBalance(currency=currency, total=0, available=0, locked=0)
    
    async def place_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        client_order_id: Optional[str] = None
    ) -> ExchangeOrder:
        """Place a market order on Binance."""
        order_id = f"binance_{uuid4().hex[:12]}"
        
        try:
            params = {
                "symbol": symbol,
                "side": side.value.upper(),
                "type": "MARKET",
                "quantity": str(quantity)
            }
            
            if client_order_id:
                params["newClientOrderId"] = client_order_id
            
            data = await self._signed_request("POST", "/api/v3/order", params)
            
            if "code" in data:
                logger.error(f"[BINANCE] Order error: {data}")
                return ExchangeOrder(
                    order_id=order_id,
                    exchange="binance",
                    symbol=symbol,
                    side=side,
                    order_type=OrderType.MARKET,
                    status=OrderStatus.REJECTED,
                    quantity=quantity
                )
            
            # Parse fills to get average price
            fills = data.get("fills", [])
            total_qty = sum(float(f["qty"]) for f in fills)
            total_cost = sum(float(f["qty"]) * float(f["price"]) for f in fills)
            avg_price = total_cost / total_qty if total_qty > 0 else 0
            total_fee = sum(float(f.get("commission", 0)) for f in fills)
            
            status_map = {
                "NEW": OrderStatus.OPEN,
                "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
                "FILLED": OrderStatus.FILLED,
                "CANCELED": OrderStatus.CANCELLED,
                "REJECTED": OrderStatus.REJECTED,
                "EXPIRED": OrderStatus.EXPIRED
            }
            
            order = ExchangeOrder(
                order_id=order_id,
                exchange="binance",
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                status=status_map.get(data.get("status"), OrderStatus.PENDING),
                quantity=quantity,
                filled_quantity=float(data.get("executedQty", 0)),
                average_price=avg_price,
                fee=total_fee,
                fee_currency=fills[0].get("commissionAsset", "") if fills else "",
                exchange_order_id=str(data.get("orderId")),
                client_order_id=data.get("clientOrderId")
            )
            
            logger.info(
                f"[BINANCE] Market order placed: {order.exchange_order_id} | "
                f"{side.value} {quantity} {symbol} @ {avg_price:.6f}"
            )
            
            return order
            
        except Exception as e:
            logger.error(f"[BINANCE] Order error: {e}")
            return ExchangeOrder(
                order_id=order_id,
                exchange="binance",
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                status=OrderStatus.REJECTED,
                quantity=quantity
            )
    
    async def place_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        price: float,
        client_order_id: Optional[str] = None
    ) -> ExchangeOrder:
        """Place a limit order on Binance."""
        order_id = f"binance_{uuid4().hex[:12]}"
        
        try:
            params = {
                "symbol": symbol,
                "side": side.value.upper(),
                "type": "LIMIT",
                "timeInForce": "GTC",
                "quantity": str(quantity),
                "price": str(price)
            }
            
            if client_order_id:
                params["newClientOrderId"] = client_order_id
            
            data = await self._signed_request("POST", "/api/v3/order", params)
            
            if "code" in data:
                logger.error(f"[BINANCE] Order error: {data}")
                return ExchangeOrder(
                    order_id=order_id,
                    exchange="binance",
                    symbol=symbol,
                    side=side,
                    order_type=OrderType.LIMIT,
                    status=OrderStatus.REJECTED,
                    quantity=quantity,
                    price=price
                )
            
            status_map = {
                "NEW": OrderStatus.OPEN,
                "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
                "FILLED": OrderStatus.FILLED,
                "CANCELED": OrderStatus.CANCELLED,
                "REJECTED": OrderStatus.REJECTED,
                "EXPIRED": OrderStatus.EXPIRED
            }
            
            order = ExchangeOrder(
                order_id=order_id,
                exchange="binance",
                symbol=symbol,
                side=side,
                order_type=OrderType.LIMIT,
                status=status_map.get(data.get("status"), OrderStatus.PENDING),
                quantity=quantity,
                price=price,
                filled_quantity=float(data.get("executedQty", 0)),
                exchange_order_id=str(data.get("orderId")),
                client_order_id=data.get("clientOrderId")
            )
            
            logger.info(
                f"[BINANCE] Limit order placed: {order.exchange_order_id} | "
                f"{side.value} {quantity} {symbol} @ {price}"
            )
            
            return order
            
        except Exception as e:
            logger.error(f"[BINANCE] Order error: {e}")
            return ExchangeOrder(
                order_id=order_id,
                exchange="binance",
                symbol=symbol,
                side=side,
                order_type=OrderType.LIMIT,
                status=OrderStatus.REJECTED,
                quantity=quantity,
                price=price
            )
    
    async def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an order."""
        try:
            params = {
                "symbol": symbol,
                "orderId": order_id
            }
            
            data = await self._signed_request("DELETE", "/api/v3/order", params)
            
            if "code" in data:
                logger.error(f"[BINANCE] Cancel error: {data}")
                return False
            
            logger.info(f"[BINANCE] Order cancelled: {order_id}")
            return True
            
        except Exception as e:
            logger.error(f"[BINANCE] Cancel error: {e}")
            return False
    
    async def get_order(self, order_id: str, symbol: str) -> Optional[ExchangeOrder]:
        """Get order status."""
        try:
            params = {
                "symbol": symbol,
                "orderId": order_id
            }
            
            data = await self._signed_request("GET", "/api/v3/order", params)
            
            if "code" in data:
                logger.error(f"[BINANCE] Order query error: {data}")
                return None
            
            status_map = {
                "NEW": OrderStatus.OPEN,
                "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
                "FILLED": OrderStatus.FILLED,
                "CANCELED": OrderStatus.CANCELLED,
                "REJECTED": OrderStatus.REJECTED,
                "EXPIRED": OrderStatus.EXPIRED
            }
            
            side = OrderSide.BUY if data.get("side") == "BUY" else OrderSide.SELL
            order_type = OrderType.MARKET if data.get("type") == "MARKET" else OrderType.LIMIT
            
            return ExchangeOrder(
                order_id=f"binance_{order_id}",
                exchange="binance",
                symbol=symbol,
                side=side,
                order_type=order_type,
                status=status_map.get(data.get("status"), OrderStatus.PENDING),
                quantity=float(data.get("origQty", 0)),
                price=float(data.get("price", 0)) if data.get("price") else None,
                filled_quantity=float(data.get("executedQty", 0)),
                average_price=float(data.get("avgPrice", 0)) if data.get("avgPrice") else 0,
                exchange_order_id=str(data.get("orderId")),
                client_order_id=data.get("clientOrderId"),
                created_at=datetime.fromtimestamp(data.get("time", 0) / 1000, tz=timezone.utc).isoformat(),
                updated_at=datetime.fromtimestamp(data.get("updateTime", 0) / 1000, tz=timezone.utc).isoformat()
            )
            
        except Exception as e:
            logger.error(f"[BINANCE] Order query error: {e}")
            return None
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[ExchangeOrder]:
        """Get all open orders."""
        try:
            params = {}
            if symbol:
                params["symbol"] = symbol
            
            data = await self._signed_request("GET", "/api/v3/openOrders", params)
            
            if isinstance(data, dict) and "code" in data:
                logger.error(f"[BINANCE] Open orders error: {data}")
                return []
            
            orders = []
            for order_data in data:
                side = OrderSide.BUY if order_data.get("side") == "BUY" else OrderSide.SELL
                order_type = OrderType.MARKET if order_data.get("type") == "MARKET" else OrderType.LIMIT
                
                orders.append(ExchangeOrder(
                    order_id=f"binance_{order_data.get('orderId')}",
                    exchange="binance",
                    symbol=order_data.get("symbol"),
                    side=side,
                    order_type=order_type,
                    status=OrderStatus.OPEN,
                    quantity=float(order_data.get("origQty", 0)),
                    price=float(order_data.get("price", 0)) if order_data.get("price") else None,
                    filled_quantity=float(order_data.get("executedQty", 0)),
                    exchange_order_id=str(order_data.get("orderId")),
                    client_order_id=order_data.get("clientOrderId")
                ))
            
            return orders
            
        except Exception as e:
            logger.error(f"[BINANCE] Open orders error: {e}")
            return []
