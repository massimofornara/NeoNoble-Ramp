"""
Coinbase Connector - Live trading integration with Coinbase Advanced Trade API.

Supports:
- Spot trading (market and limit orders)
- Account balances
- Market data (tickers, order books)

Symbol format: BTC-EUR, ETH-EUR, BNB-EUR, etc.
"""

import os
import logging
import hmac
import hashlib
import time
import json
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

logger = logging.getLogger(__name__)

# Coinbase Advanced Trade API endpoints
COINBASE_API_URL = "https://api.coinbase.com"


class CoinbaseConnector(ExchangeConnector):
    """
    Coinbase exchange connector for live trading.
    
    Features:
    - Spot market and limit orders via Advanced Trade API
    - Real-time balances
    - Market data access
    - API Key authentication (new V3 API)
    """
    
    def __init__(self):
        super().__init__("coinbase")
        self._base_url = COINBASE_API_URL
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self, api_key: str, api_secret: str, **kwargs) -> bool:
        """Initialize with Coinbase API credentials."""
        try:
            self._api_key = api_key
            self._api_secret = api_secret
            
            self._initialized = True
            logger.info("[COINBASE] Initialized")
            return True
        except Exception as e:
            logger.error(f"[COINBASE] Initialization failed: {e}")
            return False
    
    async def connect(self) -> bool:
        """Connect to Coinbase API."""
        try:
            if self._session is None:
                self._session = aiohttp.ClientSession()
            
            # Test connection with server time
            async with self._session.get(f"{self._base_url}/api/v3/brokerage/time") as response:
                if response.status == 200:
                    self._connected = True
                    logger.info("[COINBASE] Connected successfully")
                    return True
                else:
                    # Try public endpoint
                    async with self._session.get("https://api.exchange.coinbase.com/time") as pub_response:
                        if pub_response.status == 200:
                            self._connected = True
                            logger.info("[COINBASE] Connected successfully (public endpoint)")
                            return True
                    logger.error(f"[COINBASE] Connection failed: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"[COINBASE] Connection error: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from Coinbase."""
        if self._session:
            await self._session.close()
            self._session = None
        self._connected = False
        logger.info("[COINBASE] Disconnected")
    
    def _get_timestamp(self) -> str:
        """Get current timestamp."""
        return str(int(time.time()))
    
    def _generate_signature(self, timestamp: str, method: str, request_path: str, body: str = "") -> str:
        """Generate signature for authenticated requests."""
        message = timestamp + method + request_path + body
        signature = hmac.new(
            self._api_secret.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    async def _signed_request(
        self,
        method: str,
        endpoint: str,
        body: Optional[Dict] = None
    ) -> Dict:
        """Make a signed API request."""
        if not self._session:
            self._session = aiohttp.ClientSession()
        
        timestamp = self._get_timestamp()
        body_str = json.dumps(body) if body else ""
        signature = self._generate_signature(timestamp, method.upper(), endpoint, body_str)
        
        headers = {
            "CB-ACCESS-KEY": self._api_key,
            "CB-ACCESS-SIGN": signature,
            "CB-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json"
        }
        
        url = f"{self._base_url}{endpoint}"
        
        try:
            if method == "GET":
                async with self._session.get(url, headers=headers) as response:
                    return await response.json()
            elif method == "POST":
                async with self._session.post(url, headers=headers, data=body_str) as response:
                    return await response.json()
            elif method == "DELETE":
                async with self._session.delete(url, headers=headers) as response:
                    return await response.json()
        except Exception as e:
            logger.error(f"[COINBASE] Request error: {e}")
            return {"error": str(e)}
        
        return {}
    
    async def _public_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """Make a public API request."""
        if not self._session:
            self._session = aiohttp.ClientSession()
        
        # Use Exchange API for public endpoints
        url = f"https://api.exchange.coinbase.com{endpoint}"
        try:
            async with self._session.get(url, params=params) as response:
                return await response.json()
        except Exception as e:
            logger.error(f"[COINBASE] Public request error: {e}")
            return {"error": str(e)}
    
    def _normalize_symbol(self, symbol: str) -> str:
        """Convert standard symbol format to Coinbase format (BTC-EUR)."""
        # If already has dash, return as-is
        if "-" in symbol:
            return symbol
        
        # Convert BTCEUR to BTC-EUR
        # Common patterns
        conversions = {
            "BTCEUR": "BTC-EUR",
            "ETHEUR": "ETH-EUR",
            "BTCUSD": "BTC-USD",
            "ETHUSD": "ETH-USD",
            "BNBEUR": "BNB-EUR",
            "USDTEUR": "USDT-EUR",
            "USDCEUR": "USDC-EUR",
            "SOLUSDT": "SOL-USDT",
            "SOLEUR": "SOL-EUR"
        }
        
        return conversions.get(symbol.upper(), symbol)
    
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
    
    async def get_ticker(self, symbol: str) -> Optional[MarketTicker]:
        """Get current ticker for a symbol."""
        # Handle NENO symbols with virtual pricing
        if self._is_neno_symbol(symbol):
            return self._get_neno_ticker(symbol)
        
        try:
            cb_symbol = self._normalize_symbol(symbol)
            
            # Use product ticker endpoint
            data = await self._public_request(f"/products/{cb_symbol}/ticker")
            
            if "error" in data or "message" in data:
                logger.error(f"[COINBASE] Ticker error: {data}")
                return None
            
            # Get 24h stats for volume/high/low
            stats = await self._public_request(f"/products/{cb_symbol}/stats")
            
            bid = float(data.get("bid", 0))
            ask = float(data.get("ask", 0))
            
            return MarketTicker(
                symbol=symbol,
                bid=bid,
                ask=ask,
                last=float(data.get("price", 0)),
                volume_24h=float(stats.get("volume", 0)) if stats else 0,
                high_24h=float(stats.get("high", 0)) if stats else 0,
                low_24h=float(stats.get("low", 0)) if stats else 0
            )
        except Exception as e:
            logger.error(f"[COINBASE] Ticker error for {symbol}: {e}")
            return None
    
    async def get_balances(self) -> List[ExchangeBalance]:
        """Get all account balances."""
        try:
            data = await self._signed_request("GET", "/api/v3/brokerage/accounts")
            
            if "error" in data:
                logger.error(f"[COINBASE] Balance error: {data}")
                return []
            
            balances = []
            for account in data.get("accounts", []):
                available = float(account.get("available_balance", {}).get("value", 0))
                hold = float(account.get("hold", {}).get("value", 0))
                
                if available > 0 or hold > 0:
                    balances.append(ExchangeBalance(
                        currency=account.get("currency", ""),
                        total=available + hold,
                        available=available,
                        locked=hold
                    ))
            
            return balances
        except Exception as e:
            logger.error(f"[COINBASE] Balance error: {e}")
            return []
    
    async def get_balance(self, currency: str) -> Optional[ExchangeBalance]:
        """Get balance for a specific currency."""
        balances = await self.get_balances()
        for balance in balances:
            if balance.currency.upper() == currency.upper():
                return balance
        return ExchangeBalance(currency=currency, total=0, available=0, locked=0)
    
    async def place_market_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        client_order_id: Optional[str] = None
    ) -> ExchangeOrder:
        """Place a market order on Coinbase."""
        order_id = f"coinbase_{uuid4().hex[:12]}"
        cb_symbol = self._normalize_symbol(symbol)
        
        try:
            body = {
                "client_order_id": client_order_id or order_id,
                "product_id": cb_symbol,
                "side": side.value.upper(),
                "order_configuration": {
                    "market_market_ioc": {
                        "base_size": str(quantity)
                    }
                }
            }
            
            data = await self._signed_request("POST", "/api/v3/brokerage/orders", body)
            
            if "error" in data or data.get("error_response"):
                error_msg = data.get("error_response", {}).get("message", str(data))
                logger.error(f"[COINBASE] Order error: {error_msg}")
                return ExchangeOrder(
                    order_id=order_id,
                    exchange="coinbase",
                    symbol=symbol,
                    side=side,
                    order_type=OrderType.MARKET,
                    status=OrderStatus.REJECTED,
                    quantity=quantity
                )
            
            success_response = data.get("success_response", {})
            order_data = success_response or data
            
            status_map = {
                "PENDING": OrderStatus.PENDING,
                "OPEN": OrderStatus.OPEN,
                "FILLED": OrderStatus.FILLED,
                "CANCELLED": OrderStatus.CANCELLED,
                "EXPIRED": OrderStatus.EXPIRED,
                "FAILED": OrderStatus.REJECTED
            }
            
            order = ExchangeOrder(
                order_id=order_id,
                exchange="coinbase",
                symbol=symbol,
                side=side,
                order_type=OrderType.MARKET,
                status=status_map.get(order_data.get("status", "PENDING"), OrderStatus.PENDING),
                quantity=quantity,
                filled_quantity=float(order_data.get("filled_size", 0)),
                average_price=float(order_data.get("average_filled_price", 0)),
                exchange_order_id=order_data.get("order_id"),
                client_order_id=client_order_id or order_id
            )
            
            logger.info(
                f"[COINBASE] Market order placed: {order.exchange_order_id} | "
                f"{side.value} {quantity} {symbol}"
            )
            
            return order
            
        except Exception as e:
            logger.error(f"[COINBASE] Order error: {e}")
            return ExchangeOrder(
                order_id=order_id,
                exchange="coinbase",
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
        """Place a limit order on Coinbase."""
        order_id = f"coinbase_{uuid4().hex[:12]}"
        cb_symbol = self._normalize_symbol(symbol)
        
        try:
            body = {
                "client_order_id": client_order_id or order_id,
                "product_id": cb_symbol,
                "side": side.value.upper(),
                "order_configuration": {
                    "limit_limit_gtc": {
                        "base_size": str(quantity),
                        "limit_price": str(price),
                        "post_only": False
                    }
                }
            }
            
            data = await self._signed_request("POST", "/api/v3/brokerage/orders", body)
            
            if "error" in data or data.get("error_response"):
                error_msg = data.get("error_response", {}).get("message", str(data))
                logger.error(f"[COINBASE] Order error: {error_msg}")
                return ExchangeOrder(
                    order_id=order_id,
                    exchange="coinbase",
                    symbol=symbol,
                    side=side,
                    order_type=OrderType.LIMIT,
                    status=OrderStatus.REJECTED,
                    quantity=quantity,
                    price=price
                )
            
            success_response = data.get("success_response", {})
            order_data = success_response or data
            
            order = ExchangeOrder(
                order_id=order_id,
                exchange="coinbase",
                symbol=symbol,
                side=side,
                order_type=OrderType.LIMIT,
                status=OrderStatus.OPEN,
                quantity=quantity,
                price=price,
                exchange_order_id=order_data.get("order_id"),
                client_order_id=client_order_id or order_id
            )
            
            logger.info(
                f"[COINBASE] Limit order placed: {order.exchange_order_id} | "
                f"{side.value} {quantity} {symbol} @ {price}"
            )
            
            return order
            
        except Exception as e:
            logger.error(f"[COINBASE] Order error: {e}")
            return ExchangeOrder(
                order_id=order_id,
                exchange="coinbase",
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
            body = {"order_ids": [order_id]}
            data = await self._signed_request("POST", "/api/v3/brokerage/orders/batch_cancel", body)
            
            if "error" in data:
                logger.error(f"[COINBASE] Cancel error: {data}")
                return False
            
            results = data.get("results", [])
            if results and results[0].get("success"):
                logger.info(f"[COINBASE] Order cancelled: {order_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"[COINBASE] Cancel error: {e}")
            return False
    
    async def get_order(self, order_id: str, symbol: str) -> Optional[ExchangeOrder]:
        """Get order status."""
        try:
            data = await self._signed_request("GET", f"/api/v3/brokerage/orders/historical/{order_id}")
            
            if "error" in data:
                logger.error(f"[COINBASE] Order query error: {data}")
                return None
            
            order_data = data.get("order", {})
            if not order_data:
                return None
            
            status_map = {
                "PENDING": OrderStatus.PENDING,
                "OPEN": OrderStatus.OPEN,
                "FILLED": OrderStatus.FILLED,
                "CANCELLED": OrderStatus.CANCELLED,
                "EXPIRED": OrderStatus.EXPIRED,
                "FAILED": OrderStatus.REJECTED
            }
            
            side = OrderSide.BUY if order_data.get("side") == "BUY" else OrderSide.SELL
            
            config = order_data.get("order_configuration", {})
            if "market_market_ioc" in config:
                order_type = OrderType.MARKET
                price = None
            else:
                order_type = OrderType.LIMIT
                limit_config = config.get("limit_limit_gtc", {})
                price = float(limit_config.get("limit_price", 0))
            
            return ExchangeOrder(
                order_id=f"coinbase_{order_id}",
                exchange="coinbase",
                symbol=symbol,
                side=side,
                order_type=order_type,
                status=status_map.get(order_data.get("status"), OrderStatus.PENDING),
                quantity=float(order_data.get("order_configuration", {}).get("limit_limit_gtc", {}).get("base_size", 0)),
                price=price,
                filled_quantity=float(order_data.get("filled_size", 0)),
                average_price=float(order_data.get("average_filled_price", 0)),
                exchange_order_id=order_id,
                created_at=order_data.get("created_time")
            )
            
        except Exception as e:
            logger.error(f"[COINBASE] Order query error: {e}")
            return None
    
    async def get_open_orders(self, symbol: Optional[str] = None) -> List[ExchangeOrder]:
        """Get all open orders."""
        try:
            params = {"order_status": "OPEN"}
            if symbol:
                params["product_id"] = self._normalize_symbol(symbol)
            
            # Build query string
            query = "&".join([f"{k}={v}" for k, v in params.items()])
            endpoint = f"/api/v3/brokerage/orders/historical?{query}"
            
            data = await self._signed_request("GET", endpoint)
            
            if "error" in data:
                logger.error(f"[COINBASE] Open orders error: {data}")
                return []
            
            orders = []
            for order_data in data.get("orders", []):
                side = OrderSide.BUY if order_data.get("side") == "BUY" else OrderSide.SELL
                
                config = order_data.get("order_configuration", {})
                if "market_market_ioc" in config:
                    order_type = OrderType.MARKET
                    price = None
                    quantity = float(config.get("market_market_ioc", {}).get("base_size", 0))
                else:
                    order_type = OrderType.LIMIT
                    limit_config = config.get("limit_limit_gtc", {})
                    price = float(limit_config.get("limit_price", 0))
                    quantity = float(limit_config.get("base_size", 0))
                
                orders.append(ExchangeOrder(
                    order_id=f"coinbase_{order_data.get('order_id')}",
                    exchange="coinbase",
                    symbol=order_data.get("product_id", ""),
                    side=side,
                    order_type=order_type,
                    status=OrderStatus.OPEN,
                    quantity=quantity,
                    price=price,
                    filled_quantity=float(order_data.get("filled_size", 0)),
                    exchange_order_id=order_data.get("order_id")
                ))
            
            return orders
            
        except Exception as e:
            logger.error(f"[COINBASE] Open orders error: {e}")
            return []
