"""
WebSocket Routes - Real-time streaming for market data.

Provides:
- Live ticker updates for all symbols including NENO
- Order book streaming
- Trade notifications
"""

import asyncio
import json
import logging
from typing import Dict, Set, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from starlette.websockets import WebSocketState

from services.exchanges import get_connector_manager, ConnectorManager
from services.exchanges.neno_mixin import get_neno_ticker_data, is_neno_symbol

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])

# Connection manager for WebSocket clients
class ConnectionManager:
    """Manages WebSocket connections and subscriptions."""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}  # symbol -> connections
        self.connection_symbols: Dict[WebSocket, Set[str]] = {}  # connection -> symbols
        self._broadcast_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def connect(self, websocket: WebSocket, symbol: str):
        """Accept connection and subscribe to symbol."""
        await websocket.accept()
        
        if symbol not in self.active_connections:
            self.active_connections[symbol] = set()
        self.active_connections[symbol].add(websocket)
        
        if websocket not in self.connection_symbols:
            self.connection_symbols[websocket] = set()
        self.connection_symbols[websocket].add(symbol)
        
        logger.info(f"[WS] Client connected to {symbol}")
    
    def disconnect(self, websocket: WebSocket):
        """Remove connection from all subscriptions."""
        if websocket in self.connection_symbols:
            for symbol in self.connection_symbols[websocket]:
                if symbol in self.active_connections:
                    self.active_connections[symbol].discard(websocket)
            del self.connection_symbols[websocket]
        
        logger.info("[WS] Client disconnected")
    
    async def subscribe(self, websocket: WebSocket, symbol: str):
        """Subscribe to additional symbol."""
        if symbol not in self.active_connections:
            self.active_connections[symbol] = set()
        self.active_connections[symbol].add(websocket)
        
        if websocket not in self.connection_symbols:
            self.connection_symbols[websocket] = set()
        self.connection_symbols[websocket].add(symbol)
    
    async def unsubscribe(self, websocket: WebSocket, symbol: str):
        """Unsubscribe from symbol."""
        if symbol in self.active_connections:
            self.active_connections[symbol].discard(websocket)
        if websocket in self.connection_symbols:
            self.connection_symbols[websocket].discard(symbol)
    
    async def broadcast_to_symbol(self, symbol: str, message: dict):
        """Broadcast message to all subscribers of a symbol."""
        if symbol not in self.active_connections:
            return
        
        dead_connections = []
        for connection in self.active_connections[symbol]:
            try:
                if connection.client_state == WebSocketState.CONNECTED:
                    await connection.send_json(message)
            except Exception as e:
                logger.error(f"[WS] Broadcast error: {e}")
                dead_connections.append(connection)
        
        # Clean up dead connections
        for conn in dead_connections:
            self.disconnect(conn)
    
    def get_subscribed_symbols(self) -> Set[str]:
        """Get all symbols with active subscriptions."""
        return set(self.active_connections.keys())
    
    def get_connection_count(self, symbol: str = None) -> int:
        """Get number of active connections."""
        if symbol:
            return len(self.active_connections.get(symbol, set()))
        return sum(len(conns) for conns in self.active_connections.values())


# Global connection manager
manager = ConnectionManager()


async def get_manager_instance():
    """Get the connector manager instance."""
    return get_connector_manager()


@router.websocket("/ticker/{symbol}")
async def websocket_ticker(
    websocket: WebSocket,
    symbol: str
):
    """
    WebSocket endpoint for real-time ticker updates.
    
    Sends ticker updates every second for the subscribed symbol.
    Supports all symbols including NENO.
    
    Message format:
    {
        "type": "ticker",
        "symbol": "NENO-EUR",
        "data": {
            "bid": 9995.0,
            "ask": 10005.0,
            "last": 10000.0,
            "volume_24h": 1250.5,
            "timestamp": "2026-03-09T..."
        }
    }
    """
    await manager.connect(websocket, symbol)
    connector_manager = get_connector_manager()
    
    try:
        # Send initial ticker
        if is_neno_symbol(symbol):
            ticker_data = get_neno_ticker_data(symbol)
        else:
            ticker = await connector_manager.get_ticker(symbol)
            if ticker:
                ticker_data = {
                    'symbol': ticker.symbol,
                    'bid': ticker.bid,
                    'ask': ticker.ask,
                    'last': ticker.last,
                    'volume_24h': ticker.volume_24h,
                    'high_24h': ticker.high_24h,
                    'low_24h': ticker.low_24h,
                    'timestamp': ticker.timestamp
                }
            else:
                ticker_data = None
        
        if ticker_data:
            await websocket.send_json({
                "type": "ticker",
                "symbol": symbol,
                "data": ticker_data
            })
        
        # Continuous updates
        while True:
            try:
                # Wait for message or timeout
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=1.0
                    )
                    
                    # Handle client messages
                    data = json.loads(message)
                    if data.get("action") == "subscribe":
                        new_symbol = data.get("symbol")
                        if new_symbol:
                            await manager.subscribe(websocket, new_symbol)
                            await websocket.send_json({
                                "type": "subscribed",
                                "symbol": new_symbol
                            })
                    elif data.get("action") == "unsubscribe":
                        old_symbol = data.get("symbol")
                        if old_symbol:
                            await manager.unsubscribe(websocket, old_symbol)
                            await websocket.send_json({
                                "type": "unsubscribed",
                                "symbol": old_symbol
                            })
                    elif data.get("action") == "ping":
                        await websocket.send_json({"type": "pong"})
                        
                except asyncio.TimeoutError:
                    pass  # No message, continue with ticker update
                
                # Send ticker update
                if is_neno_symbol(symbol):
                    ticker_data = get_neno_ticker_data(symbol)
                else:
                    ticker = await connector_manager.get_ticker(symbol)
                    if ticker:
                        ticker_data = {
                            'symbol': ticker.symbol,
                            'bid': ticker.bid,
                            'ask': ticker.ask,
                            'last': ticker.last,
                            'volume_24h': ticker.volume_24h,
                            'high_24h': ticker.high_24h,
                            'low_24h': ticker.low_24h,
                            'timestamp': ticker.timestamp
                        }
                    else:
                        ticker_data = None
                
                if ticker_data:
                    await websocket.send_json({
                        "type": "ticker",
                        "symbol": symbol,
                        "data": ticker_data
                    })
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"[WS] Error in ticker loop: {e}")
                await asyncio.sleep(1)
                
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)


@router.websocket("/multi")
async def websocket_multi(websocket: WebSocket):
    """
    WebSocket endpoint for multiple symbol subscriptions.
    
    Subscribe to multiple symbols in one connection.
    
    Client messages:
    - {"action": "subscribe", "symbols": ["NENO-EUR", "BTC-EUR"]}
    - {"action": "unsubscribe", "symbols": ["BTC-EUR"]}
    - {"action": "ping"}
    
    Server messages:
    - {"type": "ticker", "symbol": "...", "data": {...}}
    - {"type": "subscribed", "symbols": [...]}
    - {"type": "pong"}
    """
    await websocket.accept()
    subscribed_symbols: Set[str] = set()
    connector_manager = get_connector_manager()
    
    try:
        while True:
            try:
                # Wait for message or timeout
                try:
                    message = await asyncio.wait_for(
                        websocket.receive_text(),
                        timeout=1.0
                    )
                    
                    data = json.loads(message)
                    action = data.get("action")
                    
                    if action == "subscribe":
                        new_symbols = data.get("symbols", [])
                        for sym in new_symbols:
                            subscribed_symbols.add(sym)
                        await websocket.send_json({
                            "type": "subscribed",
                            "symbols": list(subscribed_symbols)
                        })
                    
                    elif action == "unsubscribe":
                        remove_symbols = data.get("symbols", [])
                        for sym in remove_symbols:
                            subscribed_symbols.discard(sym)
                        await websocket.send_json({
                            "type": "unsubscribed",
                            "symbols": remove_symbols
                        })
                    
                    elif action == "ping":
                        await websocket.send_json({"type": "pong"})
                        
                except asyncio.TimeoutError:
                    pass
                
                # Send ticker updates for all subscribed symbols
                for symbol in subscribed_symbols:
                    if is_neno_symbol(symbol):
                        ticker_data = get_neno_ticker_data(symbol)
                    else:
                        ticker = await connector_manager.get_ticker(symbol)
                        if ticker:
                            ticker_data = {
                                'symbol': ticker.symbol,
                                'bid': ticker.bid,
                                'ask': ticker.ask,
                                'last': ticker.last,
                                'volume_24h': ticker.volume_24h,
                                'timestamp': datetime.now(timezone.utc).isoformat()
                            }
                        else:
                            continue
                    
                    await websocket.send_json({
                        "type": "ticker",
                        "symbol": symbol,
                        "data": ticker_data
                    })
                
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"[WS] Error in multi loop: {e}")
                await asyncio.sleep(1)
                
    except WebSocketDisconnect:
        pass


@router.get("/status")
async def websocket_status():
    """Get WebSocket server status."""
    return {
        "active_symbols": list(manager.get_subscribed_symbols()),
        "total_connections": manager.get_connection_count(),
        "connections_by_symbol": {
            symbol: manager.get_connection_count(symbol)
            for symbol in manager.get_subscribed_symbols()
        }
    }



# ── NENO Real-time Order Book WebSocket ──

@router.websocket("/orderbook/neno")
async def websocket_neno_orderbook(websocket: WebSocket):
    """
    WebSocket endpoint for real-time NENO order book.

    Streams simulated order book data based on dynamic pricing engine.
    Updates every 500ms with bid/ask ladder.

    Message format:
    {
        "type": "orderbook",
        "symbol": "NENO/EUR",
        "data": {
            "bids": [[price, size], ...],
            "asks": [[price, size], ...],
            "spread": 0.05,
            "mid_price": 10000.0,
            "timestamp": "..."
        }
    }
    """
    await websocket.accept()
    import random

    try:
        while True:
            try:
                # Check for client messages
                try:
                    msg = await asyncio.wait_for(websocket.receive_text(), timeout=0.5)
                    data = json.loads(msg)
                    if data.get("action") == "ping":
                        await websocket.send_json({"type": "pong"})
                        continue
                except asyncio.TimeoutError:
                    pass

                # Generate order book from dynamic pricing
                from routes.neno_exchange_routes import _get_dynamic_neno_price, NENO_BASE_PRICE
                pricing = await _get_dynamic_neno_price()
                mid_price = pricing["price"]

                # Generate realistic bid/ask ladder
                bids = []
                asks = []
                for i in range(15):
                    bid_offset = (i + 1) * random.uniform(0.5, 2.5)
                    ask_offset = (i + 1) * random.uniform(0.5, 2.5)
                    bid_size = round(random.uniform(0.01, 0.5) * (15 - i) / 15, 4)
                    ask_size = round(random.uniform(0.01, 0.5) * (15 - i) / 15, 4)
                    bids.append([round(mid_price - bid_offset, 2), bid_size])
                    asks.append([round(mid_price + ask_offset, 2), ask_size])

                spread = round(asks[0][0] - bids[0][0], 2)

                await websocket.send_json({
                    "type": "orderbook",
                    "symbol": "NENO/EUR",
                    "data": {
                        "bids": bids,
                        "asks": asks,
                        "spread": spread,
                        "spread_pct": round(spread / mid_price * 100, 4),
                        "mid_price": mid_price,
                        "base_price": NENO_BASE_PRICE,
                        "buy_volume_24h": pricing["buy_volume_24h"],
                        "sell_volume_24h": pricing["sell_volume_24h"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                })

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"[WS] NENO orderbook error: {e}")
                await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass



# ── Real-time Portfolio Tracker WebSocket ──

# Reference market prices (updated dynamically)
LIVE_PRICES = {
    "BTC": 60787.0, "ETH": 1769.0, "BNB": 555.36, "USDT": 0.92,
    "USDC": 0.92, "MATIC": 0.55, "SOL": 74.72, "NENO": 10000.0,
    "EUR": 1.0, "USD": 0.92, "XRP": 1.21, "ADA": 0.38, "DOGE": 0.082,
    "AVAX": 24.50, "DOT": 5.12, "LINK": 13.80, "UNI": 8.45,
}


def _simulate_price_tick(prices: dict) -> dict:
    """Simulate small price movements for live ticker."""
    import random
    updated = {}
    for asset, price in prices.items():
        if asset in ("EUR", "USDT", "USDC"):
            updated[asset] = price
            continue
        change_pct = random.uniform(-0.003, 0.003)  # max 0.3% per tick
        new_price = round(price * (1 + change_pct), 6)
        updated[asset] = new_price
    return updated


@router.websocket("/portfolio/{token}")
async def websocket_portfolio_tracker(websocket: WebSocket, token: str):
    """
    Real-time Portfolio Tracker WebSocket.

    Requires JWT token in URL path for authentication.
    Streams portfolio value updates every 2 seconds with live price movements.

    Message format:
    {
        "type": "portfolio_update",
        "data": {
            "total_eur": 12345.67,
            "total_24h_change_pct": 0.45,
            "assets": [{"asset":"BTC","balance":0.5,"price":60800,"eur_value":30400,"change_pct":0.02}],
            "prices": {"BTC": 60800, ...},
            "timestamp": "..."
        }
    }
    """
    await websocket.accept()

    # Authenticate via JWT
    import jwt
    import os
    try:
        secret = os.environ.get("JWT_SECRET", "secret-key")
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        # JWT uses 'sub' for user_id (standard claim)
        user_id = payload.get("sub") or payload.get("user_id")
        if not user_id:
            await websocket.send_json({"type": "error", "message": "Token non valido"})
            await websocket.close()
            return
    except Exception as e:
        logger.error(f"[WS] Portfolio auth error: {e}")
        await websocket.send_json({"type": "error", "message": "Autenticazione fallita"})
        await websocket.close()
        return

    from database.mongodb import get_database
    db = get_database()

    prices = dict(LIVE_PRICES)
    prev_total = None

    try:
        while True:
            try:
                # Check for client messages (ping/config)
                try:
                    msg = await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
                    data = json.loads(msg)
                    if data.get("action") == "ping":
                        await websocket.send_json({"type": "pong"})
                        continue
                except asyncio.TimeoutError:
                    pass

                # Fetch user wallets
                wallets = await db.wallets.find(
                    {"user_id": user_id, "balance": {"$gt": 0}}, {"_id": 0}
                ).to_list(50)

                # Simulate price ticks
                prices = _simulate_price_tick(prices)

                # Try to get real NENO price
                try:
                    from routes.neno_exchange_routes import _get_dynamic_neno_price
                    neno_pricing = await _get_dynamic_neno_price()
                    prices["NENO"] = neno_pricing["price"]
                except Exception:
                    pass

                # Calculate portfolio
                assets = []
                total_eur = 0
                for w in wallets:
                    asset = w.get("asset", "")
                    balance = w.get("balance", 0)
                    price = prices.get(asset, 0)
                    eur_value = round(balance * price, 2)
                    total_eur += eur_value

                    # Per-asset change since last tick (simulated)
                    base_price = LIVE_PRICES.get(asset, price)
                    change_pct = round(((price - base_price) / base_price * 100) if base_price else 0, 4)

                    assets.append({
                        "asset": asset,
                        "balance": round(balance, 8),
                        "price": round(price, 6),
                        "eur_value": eur_value,
                        "change_pct": change_pct,
                    })

                # Sort by EUR value desc
                assets.sort(key=lambda x: x["eur_value"], reverse=True)

                # Overall 24h change
                total_24h_change_pct = 0
                if prev_total and prev_total > 0:
                    total_24h_change_pct = round((total_eur - prev_total) / prev_total * 100, 4)
                prev_total = total_eur

                # Margin positions summary
                margin_positions = await db.margin_positions.find(
                    {"user_id": user_id, "status": "open"}, {"_id": 0}
                ).to_list(20)
                margin_total_pnl = sum(p.get("unrealized_pnl", 0) for p in margin_positions)

                await websocket.send_json({
                    "type": "portfolio_update",
                    "data": {
                        "total_eur": round(total_eur, 2),
                        "total_24h_change_pct": total_24h_change_pct,
                        "assets": assets,
                        "prices": {k: round(v, 6) for k, v in prices.items()},
                        "margin_positions_count": len(margin_positions),
                        "margin_unrealized_pnl": round(margin_total_pnl, 2),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                })

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"[WS] Portfolio tracker error: {e}")
                await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass



# ── Balance Stream WebSocket ──

_balance_subscribers: Dict[str, Set[WebSocket]] = {}  # user_id -> connections


@router.websocket("/balances/{token}")
async def ws_balance_stream(websocket: WebSocket, token: str):
    """Real-time balance updates via WebSocket. Token is JWT auth token."""
    import jwt
    import os

    secret = os.environ.get("JWT_SECRET", "")
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        user_id = payload.get("user_id")
        if not user_id:
            await websocket.close(code=4001, reason="Invalid token")
            return
    except Exception:
        await websocket.close(code=4001, reason="Auth failed")
        return

    await websocket.accept()
    if user_id not in _balance_subscribers:
        _balance_subscribers[user_id] = set()
    _balance_subscribers[user_id].add(websocket)

    logger.info(f"[WS] Balance stream connected: {user_id}")

    try:
        from database.mongodb import get_database

        while True:
            try:
                db = get_database()
                wallets = await db.wallets.find(
                    {"user_id": user_id, "balance": {"$gt": 0}}, {"_id": 0}
                ).to_list(100)

                balances = {}
                for w in wallets:
                    balances[w["asset"]] = round(w["balance"], 8)

                recent_txs = await db.neno_transactions.find(
                    {"user_id": user_id}, {"_id": 0}
                ).sort("created_at", -1).to_list(5)

                for t in recent_txs:
                    if "created_at" in t and hasattr(t["created_at"], "isoformat"):
                        t["created_at"] = t["created_at"].isoformat()

                pending_payouts = await db.payout_queue.count_documents(
                    {"user_id": user_id, "state": "payout_pending"}
                )

                await websocket.send_json({
                    "type": "balance_update",
                    "data": {
                        "balances": balances,
                        "recent_transactions": recent_txs,
                        "pending_payouts": pending_payouts,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                })

                await asyncio.sleep(2)

            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.debug(f"[WS] Balance stream error: {e}")
                await asyncio.sleep(3)

    except WebSocketDisconnect:
        pass
    finally:
        if user_id in _balance_subscribers:
            _balance_subscribers[user_id].discard(websocket)
            if not _balance_subscribers[user_id]:
                del _balance_subscribers[user_id]
        logger.info(f"[WS] Balance stream disconnected: {user_id}")


async def broadcast_balance_update(user_id: str, data: dict):
    """Broadcast balance update to all connected WebSocket clients for a user."""
    if user_id not in _balance_subscribers:
        return
    dead = set()
    for ws in _balance_subscribers[user_id]:
        try:
            await ws.send_json({"type": "balance_update", "data": data})
        except Exception:
            dead.add(ws)
    _balance_subscribers[user_id] -= dead
