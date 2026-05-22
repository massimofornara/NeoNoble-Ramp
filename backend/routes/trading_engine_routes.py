"""
Internal Trading Engine API Routes.

NeoNoble Ramp's own matching engine with:
- Order book management (bid/ask levels)
- Market and Limit order execution
- Trade history and market depth
- Trading pairs management
- Price history for charts
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone, timedelta
from enum import Enum
from collections import defaultdict
import uuid
import asyncio
import logging

from database.mongodb import get_database
from routes.auth import get_current_user

router = APIRouter(prefix="/trading", tags=["Trading Engine"])
logger = logging.getLogger(__name__)


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_LOSS = "stop_loss"
    TAKE_PROFIT = "take_profit"
    STOP_LIMIT = "stop_limit"


class OrderStatus(str, Enum):
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"


class PlaceOrderRequest(BaseModel):
    pair_id: str
    side: OrderSide
    order_type: OrderType
    quantity: float = Field(gt=0)
    price: Optional[float] = Field(None, gt=0)
    stop_price: Optional[float] = Field(None, gt=0, description="Trigger price for stop-loss/take-profit")
    leverage: Optional[float] = Field(None, ge=1, le=100, description="Leverage for margin trading")


class CancelOrderRequest(BaseModel):
    order_id: str


# === TRADING PAIRS ===

DEFAULT_PAIRS = [
    {"id": "BTC-EUR", "base": "BTC", "quote": "EUR", "base_name": "Bitcoin", "min_qty": 0.0001, "price_decimals": 2, "qty_decimals": 6, "taker_fee": 0.001, "maker_fee": 0.0005},
    {"id": "ETH-EUR", "base": "ETH", "quote": "EUR", "base_name": "Ethereum", "min_qty": 0.001, "price_decimals": 2, "qty_decimals": 5, "taker_fee": 0.001, "maker_fee": 0.0005},
    {"id": "SOL-EUR", "base": "SOL", "quote": "EUR", "base_name": "Solana", "min_qty": 0.01, "price_decimals": 2, "qty_decimals": 4, "taker_fee": 0.001, "maker_fee": 0.0005},
    {"id": "BNB-EUR", "base": "BNB", "quote": "EUR", "base_name": "BNB", "min_qty": 0.01, "price_decimals": 2, "qty_decimals": 4, "taker_fee": 0.001, "maker_fee": 0.0005},
    {"id": "XRP-EUR", "base": "XRP", "quote": "EUR", "base_name": "XRP", "min_qty": 1.0, "price_decimals": 4, "qty_decimals": 2, "taker_fee": 0.001, "maker_fee": 0.0005},
    {"id": "ADA-EUR", "base": "ADA", "quote": "EUR", "base_name": "Cardano", "min_qty": 1.0, "price_decimals": 4, "qty_decimals": 2, "taker_fee": 0.001, "maker_fee": 0.0005},
    {"id": "DOGE-EUR", "base": "DOGE", "quote": "EUR", "base_name": "Dogecoin", "min_qty": 10.0, "price_decimals": 5, "qty_decimals": 1, "taker_fee": 0.001, "maker_fee": 0.0005},
    {"id": "DOT-EUR", "base": "DOT", "quote": "EUR", "base_name": "Polkadot", "min_qty": 0.1, "price_decimals": 3, "qty_decimals": 3, "taker_fee": 0.001, "maker_fee": 0.0005},
    {"id": "LINK-EUR", "base": "LINK", "quote": "EUR", "base_name": "Chainlink", "min_qty": 0.1, "price_decimals": 3, "qty_decimals": 3, "taker_fee": 0.001, "maker_fee": 0.0005},
    {"id": "AVAX-EUR", "base": "AVAX", "quote": "EUR", "base_name": "Avalanche", "min_qty": 0.1, "price_decimals": 3, "qty_decimals": 3, "taker_fee": 0.001, "maker_fee": 0.0005},
    {"id": "NENO-EUR", "base": "NENO", "quote": "EUR", "base_name": "NeoNoble", "min_qty": 1.0, "price_decimals": 4, "qty_decimals": 2, "taker_fee": 0.0008, "maker_fee": 0.0003},
    {"id": "NENO-USDT", "base": "NENO", "quote": "USDT", "base_name": "NeoNoble", "min_qty": 1.0, "price_decimals": 4, "qty_decimals": 2, "taker_fee": 0.0008, "maker_fee": 0.0003},
    {"id": "BTC-USDT", "base": "BTC", "quote": "USDT", "base_name": "Bitcoin", "min_qty": 0.0001, "price_decimals": 2, "qty_decimals": 6, "taker_fee": 0.001, "maker_fee": 0.0005},
    {"id": "ETH-USDT", "base": "ETH", "quote": "USDT", "base_name": "Ethereum", "min_qty": 0.001, "price_decimals": 2, "qty_decimals": 5, "taker_fee": 0.001, "maker_fee": 0.0005},
    {"id": "ETH-BTC", "base": "ETH", "quote": "BTC", "base_name": "Ethereum", "min_qty": 0.001, "price_decimals": 6, "qty_decimals": 5, "taker_fee": 0.001, "maker_fee": 0.0005},
]

# Reference prices for seeding order book
REF_PRICES = {
    "BTC-EUR": 60787.0, "ETH-EUR": 1769.0, "SOL-EUR": 74.72,
    "BNB-EUR": 555.36, "XRP-EUR": 1.21, "ADA-EUR": 0.38,
    "DOGE-EUR": 0.082, "DOT-EUR": 4.20, "LINK-EUR": 12.50,
    "AVAX-EUR": 18.50, "NENO-EUR": 0.50, "NENO-USDT": 0.54,
    "BTC-USDT": 66073.0, "ETH-USDT": 1922.0, "ETH-BTC": 0.0291,
}


@router.get("/pairs")
async def get_trading_pairs():
    """Get all available trading pairs."""
    db = get_database()
    pairs = await db.trading_engine_pairs.find({}, {"_id": 0}).to_list(100)
    if not pairs:
        for p in DEFAULT_PAIRS:
            p["is_active"] = True
            p["created_at"] = datetime.now(timezone.utc).isoformat()
        await db.trading_engine_pairs.insert_many([{**p, "_id": p["id"]} for p in DEFAULT_PAIRS])
        pairs = DEFAULT_PAIRS
    return {"pairs": pairs, "total": len(pairs)}


@router.get("/pairs/{pair_id}/ticker")
async def get_pair_ticker(pair_id: str):
    """Get current ticker for a trading pair."""
    db = get_database()
    last_trade = await db.trades.find_one(
        {"pair_id": pair_id}, sort=[("created_at", -1)]
    )
    last_price = last_trade["price"] if last_trade else REF_PRICES.get(pair_id, 1.0)

    bids = await db.order_book.find(
        {"pair_id": pair_id, "side": "buy", "status": "open"}
    ).sort("price", -1).limit(1).to_list(1)
    asks = await db.order_book.find(
        {"pair_id": pair_id, "side": "sell", "status": "open"}
    ).sort("price", 1).limit(1).to_list(1)

    best_bid = bids[0]["price"] if bids else last_price * 0.999
    best_ask = asks[0]["price"] if asks else last_price * 1.001

    day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    vol_pipeline = [
        {"$match": {"pair_id": pair_id, "created_at": {"$gte": day_ago}}},
        {"$group": {"_id": None, "vol": {"$sum": "$quantity"}, "count": {"$sum": 1}}}
    ]
    vol_data = await db.trades.aggregate(vol_pipeline).to_list(1)
    volume_24h = vol_data[0]["vol"] if vol_data else 0

    first_trade_24h = await db.trades.find_one(
        {"pair_id": pair_id, "created_at": {"$gte": day_ago}}, sort=[("created_at", 1)]
    )
    open_price = first_trade_24h["price"] if first_trade_24h else last_price
    change_24h = ((last_price - open_price) / open_price * 100) if open_price else 0

    return {
        "pair_id": pair_id,
        "last_price": last_price,
        "best_bid": round(best_bid, 6),
        "best_ask": round(best_ask, 6),
        "spread": round(best_ask - best_bid, 6),
        "spread_pct": round((best_ask - best_bid) / last_price * 100, 4),
        "volume_24h": round(volume_24h, 4),
        "change_24h": round(change_24h, 2),
        "high_24h": last_price * 1.02,
        "low_24h": last_price * 0.98,
    }


@router.get("/pairs/{pair_id}/orderbook")
async def get_order_book(pair_id: str, depth: int = Query(20, ge=1, le=100)):
    """Get order book with bid/ask levels."""
    db = get_database()

    bids_cursor = db.order_book.aggregate([
        {"$match": {"pair_id": pair_id, "side": "buy", "status": "open"}},
        {"$group": {"_id": "$price", "quantity": {"$sum": "$remaining_qty"}, "orders": {"$sum": 1}}},
        {"$sort": {"_id": -1}},
        {"$limit": depth}
    ])
    asks_cursor = db.order_book.aggregate([
        {"$match": {"pair_id": pair_id, "side": "sell", "status": "open"}},
        {"$group": {"_id": "$price", "quantity": {"$sum": "$remaining_qty"}, "orders": {"$sum": 1}}},
        {"$sort": {"_id": 1}},
        {"$limit": depth}
    ])

    bids_raw = await bids_cursor.to_list(depth)
    asks_raw = await asks_cursor.to_list(depth)

    bids = [{"price": b["_id"], "quantity": round(b["quantity"], 6), "orders": b["orders"]} for b in bids_raw]
    asks = [{"price": a["_id"], "quantity": round(a["quantity"], 6), "orders": a["orders"]} for a in asks_raw]

    if not bids and not asks:
        ref = REF_PRICES.get(pair_id, 1.0)
        bids = [{"price": round(ref * (1 - i * 0.001), 6), "quantity": round(0.5 + i * 0.3, 4), "orders": 1} for i in range(min(depth, 10))]
        asks = [{"price": round(ref * (1 + (i + 1) * 0.001), 6), "quantity": round(0.5 + i * 0.3, 4), "orders": 1} for i in range(min(depth, 10))]

    return {"pair_id": pair_id, "bids": bids, "asks": asks, "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/pairs/{pair_id}/depth")
async def get_market_depth(pair_id: str, depth: int = Query(50, ge=1, le=200)):
    """Get market depth for visualization."""
    ob = await get_order_book(pair_id, depth)
    cum_bid_vol = 0
    cum_ask_vol = 0
    bid_depth = []
    ask_depth = []
    for b in ob["bids"]:
        cum_bid_vol += b["quantity"]
        bid_depth.append({"price": b["price"], "cumulative": round(cum_bid_vol, 4)})
    for a in ob["asks"]:
        cum_ask_vol += a["quantity"]
        ask_depth.append({"price": a["price"], "cumulative": round(cum_ask_vol, 4)})
    return {"pair_id": pair_id, "bids": bid_depth, "asks": ask_depth}


# === ORDER PLACEMENT & MATCHING ===

async def _match_order(db, order: dict) -> list:
    """Core matching engine. Matches an order against the order book."""
    trades = []
    side = order["side"]
    opposite_side = "sell" if side == "buy" else "buy"
    sort_dir = 1 if side == "buy" else -1  # buy matches lowest asks, sell matches highest bids

    while order["remaining_qty"] > 0:
        query = {
            "pair_id": order["pair_id"],
            "side": opposite_side,
            "status": "open",
            "user_id": {"$ne": order["user_id"]},
        }

        if order["order_type"] == "limit":
            if side == "buy":
                query["price"] = {"$lte": order["price"]}
            else:
                query["price"] = {"$gte": order["price"]}

        best_match = await db.order_book.find_one(query, sort=[("price", sort_dir), ("created_at", 1)])
        if not best_match:
            break

        fill_qty = min(order["remaining_qty"], best_match["remaining_qty"])
        fill_price = best_match["price"]

        trade = {
            "id": str(uuid.uuid4()),
            "pair_id": order["pair_id"],
            "price": fill_price,
            "quantity": fill_qty,
            "buyer_order_id": order["id"] if side == "buy" else best_match["id"],
            "seller_order_id": best_match["id"] if side == "buy" else order["id"],
            "buyer_id": order["user_id"] if side == "buy" else best_match["user_id"],
            "seller_id": best_match["user_id"] if side == "buy" else order["user_id"],
            "taker_side": side,
            "created_at": datetime.now(timezone.utc),
        }

        order["remaining_qty"] -= fill_qty
        order["filled_qty"] = order.get("filled_qty", 0) + fill_qty

        new_match_remaining = best_match["remaining_qty"] - fill_qty
        match_status = "filled" if new_match_remaining <= 0 else "partially_filled"
        await db.order_book.update_one(
            {"id": best_match["id"]},
            {"$set": {"remaining_qty": new_match_remaining, "status": match_status, "filled_qty": best_match.get("filled_qty", 0) + fill_qty}}
        )

        await db.trades.insert_one({**trade, "_id": trade["id"]})
        trades.append(trade)

    if order["remaining_qty"] <= 0:
        order["status"] = "filled"
    elif order["filled_qty"] > 0:
        order["status"] = "partially_filled"

    return trades


@router.post("/orders")
async def place_order(request: PlaceOrderRequest, current_user: dict = Depends(get_current_user)):
    """Place a buy or sell order."""
    db = get_database()

    pair = await db.trading_engine_pairs.find_one({"id": request.pair_id})
    if not pair:
        raise HTTPException(status_code=404, detail=f"Trading pair {request.pair_id} not found")

    if request.order_type in (OrderType.STOP_LOSS, OrderType.TAKE_PROFIT, OrderType.STOP_LIMIT):
        if not request.stop_price:
            raise HTTPException(status_code=400, detail="Stop price required for stop-loss/take-profit orders")
        if request.order_type == OrderType.STOP_LIMIT and not request.price:
            raise HTTPException(status_code=400, detail="Limit price required for stop-limit orders")

    if request.order_type == OrderType.LIMIT and not request.price:
        raise HTTPException(status_code=400, detail="Price required for limit orders")

    if request.quantity < pair.get("min_qty", 0):
        raise HTTPException(status_code=400, detail=f"Minimum quantity: {pair.get('min_qty', 0)}")

    order = {
        "id": str(uuid.uuid4()),
        "pair_id": request.pair_id,
        "user_id": current_user["user_id"],
        "side": request.side.value,
        "order_type": request.order_type.value,
        "quantity": request.quantity,
        "price": request.price if request.order_type in (OrderType.LIMIT, OrderType.STOP_LIMIT) else None,
        "stop_price": request.stop_price,
        "leverage": request.leverage,
        "remaining_qty": request.quantity,
        "filled_qty": 0.0,
        "status": "open",
        "created_at": datetime.now(timezone.utc),
    }

    # Stop-loss/take-profit are conditional orders - store as pending
    if request.order_type in (OrderType.STOP_LOSS, OrderType.TAKE_PROFIT, OrderType.STOP_LIMIT):
        order["status"] = "pending_trigger"
        order_doc = {k: v for k, v in order.items()}
        order_doc["_id"] = order["id"]
        if isinstance(order_doc.get("created_at"), datetime):
            order_doc["created_at"] = order_doc["created_at"].isoformat()
        await db.order_book.insert_one(order_doc)
        return {
            "order": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in order.items()},
            "trades": [],
            "message": f"Conditional order placed: triggers at {request.stop_price}"
        }

    trades = await _match_order(db, order)

    if order["status"] == "open" and order["order_type"] == "market":
        ref_price = REF_PRICES.get(request.pair_id, 1.0)
        slippage = 0.002 if request.side == OrderSide.BUY else -0.002
        fill_price = ref_price * (1 + slippage)

        trade = {
            "id": str(uuid.uuid4()),
            "pair_id": request.pair_id,
            "price": round(fill_price, 6),
            "quantity": order["remaining_qty"],
            "buyer_order_id": order["id"] if request.side == OrderSide.BUY else "market_maker",
            "seller_order_id": "market_maker" if request.side == OrderSide.BUY else order["id"],
            "buyer_id": current_user["user_id"] if request.side == OrderSide.BUY else "system",
            "seller_id": "system" if request.side == OrderSide.BUY else current_user["user_id"],
            "taker_side": request.side.value,
            "created_at": datetime.now(timezone.utc),
        }
        await db.trades.insert_one({**trade, "_id": trade["id"]})
        trades.append(trade)
        order["filled_qty"] = order["quantity"]
        order["remaining_qty"] = 0
        order["status"] = "filled"

    order_doc = {k: v for k, v in order.items()}
    order_doc["_id"] = order["id"]
    if isinstance(order_doc.get("created_at"), datetime):
        order_doc["created_at"] = order_doc["created_at"].isoformat()
    await db.order_book.insert_one(order_doc)

    trade_summaries = []
    for t in trades:
        ts = {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in t.items() if k != "_id"}
        trade_summaries.append(ts)

    return {
        "order": {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in order.items()},
        "trades": trade_summaries,
        "message": f"Order {order['status']}: {len(trades)} trade(s) executed"
    }


@router.get("/orders/my")
async def get_my_orders(
    pair_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user)
):
    """Get current user's orders."""
    db = get_database()
    query = {"user_id": current_user["user_id"]}
    if pair_id:
        query["pair_id"] = pair_id
    if status:
        query["status"] = status

    orders = await db.order_book.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"orders": orders, "total": len(orders)}


@router.post("/orders/cancel")
async def cancel_order(request: CancelOrderRequest, current_user: dict = Depends(get_current_user)):
    """Cancel an open order."""
    db = get_database()
    order = await db.order_book.find_one({"id": request.order_id, "user_id": current_user["user_id"]})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    if order["status"] not in ("open", "partially_filled", "pending_trigger"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel {order['status']} order")

    await db.order_book.update_one({"id": request.order_id}, {"$set": {"status": "cancelled"}})
    return {"message": "Order cancelled", "order_id": request.order_id}


@router.get("/trades/{pair_id}")
async def get_recent_trades(pair_id: str, limit: int = Query(50, ge=1, le=200)):
    """Get recent trades for a pair."""
    db = get_database()
    trades = await db.trades.find(
        {"pair_id": pair_id}, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)

    for t in trades:
        if "created_at" in t and hasattr(t["created_at"], "isoformat"):
            t["created_at"] = t["created_at"].isoformat()

    return {"trades": trades, "pair_id": pair_id}


@router.get("/pairs/{pair_id}/candles")
async def get_candles(
    pair_id: str,
    interval: str = Query("1h", description="1m, 5m, 15m, 1h, 4h, 1d"),
    limit: int = Query(100, ge=1, le=500)
):
    """Get OHLCV candle data for charts."""
    db = get_database()
    interval_map = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}
    seconds = interval_map.get(interval, 3600)

    ref_price = REF_PRICES.get(pair_id, 1.0)
    now = datetime.now(timezone.utc)
    candles = []

    trades = await db.trades.find({"pair_id": pair_id}).sort("created_at", -1).limit(1000).to_list(1000)

    if len(trades) < 10:
        import random
        random.seed(hash(pair_id))
        price = ref_price
        for i in range(limit):
            t = now - timedelta(seconds=seconds * (limit - i))
            change = random.uniform(-0.015, 0.015)
            o = price
            h = o * (1 + abs(random.uniform(0, 0.008)))
            l = o * (1 - abs(random.uniform(0, 0.008)))
            c = o * (1 + change)
            v = random.uniform(0.5, 50.0)
            candles.append({
                "time": int(t.timestamp()),
                "open": round(o, 6), "high": round(max(h, o, c), 6),
                "low": round(min(l, o, c), 6), "close": round(c, 6),
                "volume": round(v, 4)
            })
            price = c
    else:
        trade_buckets = defaultdict(list)
        for t in trades:
            ts = t["created_at"] if isinstance(t["created_at"], datetime) else datetime.fromisoformat(str(t["created_at"]))
            bucket = int(ts.timestamp() // seconds) * seconds
            trade_buckets[bucket].append(t)

        for bucket_ts in sorted(trade_buckets.keys())[-limit:]:
            bucket_trades = trade_buckets[bucket_ts]
            prices = [t["price"] for t in bucket_trades]
            volumes = [t["quantity"] for t in bucket_trades]
            candles.append({
                "time": bucket_ts,
                "open": prices[0], "high": max(prices),
                "low": min(prices), "close": prices[-1],
                "volume": round(sum(volumes), 4)
            })

    return {"pair_id": pair_id, "interval": interval, "candles": candles}


@router.get("/stats")
async def get_trading_stats(current_user: dict = Depends(get_current_user)):
    """Get trading statistics."""
    db = get_database()
    if current_user.get("role") != "ADMIN":
        raise HTTPException(status_code=403, detail="Admin access required")

    total_trades = await db.trades.count_documents({})
    total_orders = await db.order_book.count_documents({})
    open_orders = await db.order_book.count_documents({"status": "open"})
    pairs = await db.trading_engine_pairs.count_documents({})

    day_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    trades_24h = await db.trades.count_documents({"created_at": {"$gte": day_ago}})

    return {
        "total_trades": total_trades,
        "total_orders": total_orders,
        "open_orders": open_orders,
        "trading_pairs": pairs,
        "trades_24h": trades_24h,
    }



# === FULL MARGIN TRADING ===

class MarginAccountRequest(BaseModel):
    leverage: float = Field(default=2.0, ge=1, le=100)
    collateral_asset: str = Field(default="EUR")
    collateral_amount: float = Field(default=0, ge=0)


class OpenPositionRequest(BaseModel):
    pair_id: str
    side: OrderSide
    quantity: float = Field(gt=0)
    leverage: float = Field(ge=1, le=100)
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class ClosePositionRequest(BaseModel):
    position_id: str


class DepositMarginRequest(BaseModel):
    asset: str = Field(default="EUR")
    amount: float = Field(gt=0)


@router.post("/margin/account")
async def create_margin_account(request: MarginAccountRequest, current_user: dict = Depends(get_current_user)):
    """Create or update margin trading account."""
    db = get_database()
    existing = await db.margin_accounts.find_one({"user_id": current_user["user_id"]})
    if existing:
        await db.margin_accounts.update_one(
            {"user_id": current_user["user_id"]},
            {"$set": {"max_leverage": request.leverage}}
        )
        return {"message": "Margin account updated", "max_leverage": request.leverage}

    account = {
        "id": str(uuid.uuid4()),
        "user_id": current_user["user_id"],
        "max_leverage": request.leverage,
        "collateral_asset": request.collateral_asset,
        "margin_balance": 0.0,
        "borrowed_amount": 0.0,
        "unrealized_pnl": 0.0,
        "maintenance_margin_pct": 0.05,
        "margin_level": 0.0,
        "status": "active",
        "total_positions": 0,
        "total_realized_pnl": 0.0,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.margin_accounts.insert_one({**account, "_id": account["id"]})
    return {"message": "Margin account created", "account": account}


@router.post("/margin/deposit")
async def deposit_margin(request: DepositMarginRequest, current_user: dict = Depends(get_current_user)):
    """Deposit collateral into margin account from wallet."""
    db = get_database()
    uid = current_user["user_id"]
    account = await db.margin_accounts.find_one({"user_id": uid})
    if not account:
        raise HTTPException(status_code=404, detail="Margin account not found. Create one first.")
    wallet = await db.wallets.find_one({"user_id": uid, "asset": request.asset.upper()})
    balance = wallet.get("balance", 0) if wallet else 0
    if balance < request.amount:
        raise HTTPException(status_code=400, detail=f"Saldo {request.asset} insufficiente: {balance}")
    await db.wallets.update_one({"user_id": uid, "asset": request.asset.upper()}, {"$inc": {"balance": -request.amount}})
    await db.margin_accounts.update_one({"user_id": uid}, {"$inc": {"margin_balance": request.amount}})
    return {"message": f"Depositati {request.amount} {request.asset} nel margin account", "new_margin_balance": (account.get("margin_balance", 0) + request.amount)}


@router.post("/margin/withdraw")
async def withdraw_margin(request: DepositMarginRequest, current_user: dict = Depends(get_current_user)):
    """Withdraw collateral from margin account to wallet."""
    db = get_database()
    uid = current_user["user_id"]
    account = await db.margin_accounts.find_one({"user_id": uid})
    if not account:
        raise HTTPException(status_code=404, detail="Margin account not found")
    available = account.get("margin_balance", 0) - account.get("borrowed_amount", 0)
    if available < request.amount:
        raise HTTPException(status_code=400, detail=f"Margine disponibile insufficiente: {available:.2f}")
    await db.margin_accounts.update_one({"user_id": uid}, {"$inc": {"margin_balance": -request.amount}})
    await db.wallets.update_one(
        {"user_id": uid, "asset": request.asset.upper()},
        {"$inc": {"balance": request.amount}, "$setOnInsert": {"user_id": uid, "asset": request.asset.upper()}},
        upsert=True,
    )
    return {"message": f"Prelevati {request.amount} {request.asset} dal margin account"}


@router.post("/margin/open")
async def open_margin_position(request: OpenPositionRequest, current_user: dict = Depends(get_current_user)):
    """Open a leveraged margin position."""
    db = get_database()
    uid = current_user["user_id"]
    account = await db.margin_accounts.find_one({"user_id": uid})
    if not account or account.get("status") != "active":
        raise HTTPException(status_code=400, detail="Margin account non attivo")
    if request.leverage > account.get("max_leverage", 10):
        raise HTTPException(status_code=400, detail=f"Leverage massimo: {account['max_leverage']}x")
    ref_price = REF_PRICES.get(request.pair_id)
    if not ref_price:
        raise HTTPException(status_code=404, detail="Trading pair not found")
    notional = ref_price * request.quantity
    required_margin = notional / request.leverage
    margin_balance = account.get("margin_balance", 0)
    if margin_balance < required_margin:
        raise HTTPException(status_code=400, detail=f"Margine insufficiente: serve {required_margin:.2f}, disponibile {margin_balance:.2f}")
    liq_price = ref_price * (1 - 1 / request.leverage * 0.9) if request.side == OrderSide.BUY else ref_price * (1 + 1 / request.leverage * 0.9)
    position = {
        "id": str(uuid.uuid4()),
        "user_id": uid,
        "pair_id": request.pair_id,
        "side": request.side.value,
        "quantity": request.quantity,
        "entry_price": ref_price,
        "current_price": ref_price,
        "leverage": request.leverage,
        "notional_value": round(notional, 2),
        "margin_used": round(required_margin, 2),
        "unrealized_pnl": 0.0,
        "unrealized_pnl_pct": 0.0,
        "liquidation_price": round(liq_price, 2),
        "stop_loss": request.stop_loss,
        "take_profit": request.take_profit,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.margin_positions.insert_one({**position, "_id": position["id"]})
    await db.margin_accounts.update_one(
        {"user_id": uid},
        {"$inc": {"margin_balance": -required_margin, "borrowed_amount": notional - required_margin, "total_positions": 1}},
    )
    return {"message": f"Posizione {request.side.value} {request.quantity} {request.pair_id} @ {ref_price} aperta con leva {request.leverage}x", "position": position}


@router.post("/margin/close")
async def close_margin_position(request: ClosePositionRequest, current_user: dict = Depends(get_current_user)):
    """Close a margin position and realize PnL."""
    db = get_database()
    uid = current_user["user_id"]
    position = await db.margin_positions.find_one({"id": request.position_id, "user_id": uid, "status": "open"})
    if not position:
        raise HTTPException(status_code=404, detail="Posizione non trovata o gia chiusa")
    current_price = REF_PRICES.get(position["pair_id"], position["entry_price"])
    qty = position["quantity"]
    entry = position["entry_price"]
    if position["side"] == "buy":
        pnl = (current_price - entry) * qty
    else:
        pnl = (entry - current_price) * qty
    pnl_pct = (pnl / position["margin_used"]) * 100 if position.get("margin_used", 0) > 0 else 0
    margin_return = position["margin_used"] + pnl
    await db.margin_positions.update_one(
        {"id": request.position_id},
        {"$set": {"status": "closed", "exit_price": current_price, "realized_pnl": round(pnl, 2), "realized_pnl_pct": round(pnl_pct, 2), "closed_at": datetime.now(timezone.utc).isoformat()}},
    )
    borrowed_return = position.get("notional_value", 0) - position["margin_used"]
    await db.margin_accounts.update_one(
        {"user_id": uid},
        {"$inc": {"margin_balance": max(margin_return, 0), "borrowed_amount": -borrowed_return, "total_realized_pnl": pnl}},
    )
    return {"message": f"Posizione chiusa @ {current_price}. PnL: {pnl:+.2f} EUR ({pnl_pct:+.1f}%)", "realized_pnl": round(pnl, 2), "margin_returned": round(max(margin_return, 0), 2)}


@router.get("/margin/account")
async def get_margin_account(current_user: dict = Depends(get_current_user)):
    """Get margin account with live PnL calculation."""
    db = get_database()
    account = await db.margin_accounts.find_one({"user_id": current_user["user_id"]}, {"_id": 0})
    if not account:
        return {"message": "No margin account", "account": None}
    positions = await db.margin_positions.find({"user_id": current_user["user_id"], "status": "open"}, {"_id": 0}).to_list(100)
    total_unrealized = 0
    for p in positions:
        cp = REF_PRICES.get(p["pair_id"], p["entry_price"])
        pnl = (cp - p["entry_price"]) * p["quantity"] if p["side"] == "buy" else (p["entry_price"] - cp) * p["quantity"]
        p["current_price"] = cp
        p["unrealized_pnl"] = round(pnl, 2)
        p["unrealized_pnl_pct"] = round((pnl / p["margin_used"]) * 100, 2) if p.get("margin_used", 0) > 0 else 0
        total_unrealized += pnl
    account["unrealized_pnl"] = round(total_unrealized, 2)
    equity = account.get("margin_balance", 0) + total_unrealized
    borrowed = account.get("borrowed_amount", 0)
    account["equity"] = round(equity, 2)
    account["margin_level"] = round((equity / borrowed * 100), 2) if borrowed > 0 else 999.99
    account["open_positions"] = positions
    return {"account": account}


@router.get("/margin/positions")
async def get_margin_positions(current_user: dict = Depends(get_current_user)):
    """Get all margin positions (open + closed)."""
    db = get_database()
    positions = await db.margin_positions.find({"user_id": current_user["user_id"]}, {"_id": 0}).sort("created_at", -1).to_list(100)
    for p in positions:
        if p.get("status") == "open":
            cp = REF_PRICES.get(p["pair_id"], p["entry_price"])
            pnl = (cp - p["entry_price"]) * p["quantity"] if p["side"] == "buy" else (p["entry_price"] - cp) * p["quantity"]
            p["current_price"] = cp
            p["unrealized_pnl"] = round(pnl, 2)
    return {"positions": positions}


# === PAPER TRADING ===

class PaperTradeRequest(BaseModel):
    pair_id: str
    side: OrderSide
    order_type: str = "market"
    quantity: float = Field(gt=0)
    price: Optional[float] = None

@router.post("/paper/trade")
async def place_paper_trade(request: PaperTradeRequest, current_user: dict = Depends(get_current_user)):
    """Place a paper trade (simulated, no real execution)."""
    db = get_database()
    ref_price = REF_PRICES.get(request.pair_id)
    if not ref_price:
        raise HTTPException(status_code=404, detail="Trading pair not found")

    exec_price = request.price if request.price else ref_price
    if request.order_type == "market":
        slippage = 0.001 if request.side == OrderSide.BUY else -0.001
        exec_price = ref_price * (1 + slippage)

    pnl = 0.0
    trade = {
        "id": str(uuid.uuid4()),
        "user_id": current_user["user_id"],
        "pair_id": request.pair_id,
        "side": request.side.value,
        "order_type": request.order_type,
        "quantity": request.quantity,
        "price": round(exec_price, 6),
        "total_value": round(exec_price * request.quantity, 2),
        "pnl": pnl,
        "is_paper": True,
        "status": "filled",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Update paper portfolio
    portfolio_key = f"{request.pair_id}_{request.side.value}"
    await db.paper_trades.insert_one({**trade, "_id": trade["id"]})

    await db.paper_portfolio.update_one(
        {"user_id": current_user["user_id"]},
        {
            "$inc": {"total_trades": 1, "total_volume": trade["total_value"]},
            "$setOnInsert": {"user_id": current_user["user_id"], "initial_balance": 100000.0, "created_at": datetime.now(timezone.utc).isoformat()},
        },
        upsert=True,
    )

    return {"trade": trade, "message": f"Paper trade executed: {request.side.value} {request.quantity} @ {exec_price:.4f}"}


@router.get("/paper/portfolio")
async def get_paper_portfolio(current_user: dict = Depends(get_current_user)):
    """Get paper trading portfolio."""
    db = get_database()
    portfolio = await db.paper_portfolio.find_one(
        {"user_id": current_user["user_id"]}, {"_id": 0}
    )
    if not portfolio:
        return {
            "portfolio": {"initial_balance": 100000.0, "current_balance": 100000.0, "total_trades": 0, "total_volume": 0, "pnl": 0},
            "recent_trades": []
        }

    trades = await db.paper_trades.find(
        {"user_id": current_user["user_id"]}, {"_id": 0}
    ).sort("created_at", -1).limit(50).to_list(50)

    return {"portfolio": portfolio, "recent_trades": trades}


@router.delete("/paper/reset")
async def reset_paper_portfolio(current_user: dict = Depends(get_current_user)):
    """Reset paper trading portfolio."""
    db = get_database()
    await db.paper_trades.delete_many({"user_id": current_user["user_id"]})
    await db.paper_portfolio.delete_many({"user_id": current_user["user_id"]})
    return {"message": "Paper portfolio reset to €100,000"}
