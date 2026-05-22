"""
Testing Trading Engine and Public API Routes - Iteration 5

Features tested:
1. Trading pairs - GET /api/trading/pairs (15 pairs including NENO pairs)
2. Ticker data - GET /api/trading/pairs/{pair_id}/ticker
3. Order book - GET /api/trading/pairs/{pair_id}/orderbook
4. Candle data - GET /api/trading/pairs/{pair_id}/candles
5. Place orders - POST /api/trading/orders (market/limit buy/sell)
6. My orders - GET /api/trading/orders/my
7. Cancel orders - POST /api/trading/orders/cancel
8. Recent trades - GET /api/trading/trades/{pair_id}
9. Public API docs - GET /api/public/v1/docs
10. Public market data - GET /api/public/v1/market/coins
11. Public pairs - GET /api/public/v1/pairs
12. Public ticker - GET /api/public/v1/market/ticker/{pair_id}
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token for admin user"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


class TestTradingPairs:
    """Trading pairs endpoint tests"""
    
    def test_get_trading_pairs(self, api_client):
        """Test GET /api/trading/pairs returns 15 trading pairs"""
        response = api_client.get(f"{BASE_URL}/api/trading/pairs")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "pairs" in data
        assert "total" in data
        assert data["total"] >= 15, f"Expected at least 15 pairs, got {data['total']}"
        
        # Verify NENO pairs exist
        pair_ids = [p["id"] for p in data["pairs"]]
        assert "NENO-EUR" in pair_ids, "NENO-EUR pair missing"
        assert "NENO-USDT" in pair_ids, "NENO-USDT pair missing"
        assert "BTC-EUR" in pair_ids, "BTC-EUR pair missing"
        assert "ETH-EUR" in pair_ids, "ETH-EUR pair missing"
        print(f"✓ GET /api/trading/pairs: {data['total']} pairs including NENO pairs")

    def test_trading_pair_structure(self, api_client):
        """Verify trading pair data structure"""
        response = api_client.get(f"{BASE_URL}/api/trading/pairs")
        assert response.status_code == 200
        
        data = response.json()
        pair = data["pairs"][0]
        
        # Check required fields
        required_fields = ["id", "base", "quote", "base_name", "min_qty", "price_decimals", "qty_decimals", "taker_fee", "maker_fee"]
        for field in required_fields:
            assert field in pair, f"Missing field: {field}"
        
        print(f"✓ Trading pair structure verified with fields: {list(pair.keys())}")


class TestTicker:
    """Ticker endpoint tests"""
    
    def test_get_btc_eur_ticker(self, api_client):
        """Test GET /api/trading/pairs/BTC-EUR/ticker"""
        response = api_client.get(f"{BASE_URL}/api/trading/pairs/BTC-EUR/ticker")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "pair_id" in data
        assert data["pair_id"] == "BTC-EUR"
        assert "last_price" in data
        assert "best_bid" in data
        assert "best_ask" in data
        assert "spread" in data
        assert "volume_24h" in data
        
        # Verify numeric values
        assert isinstance(data["last_price"], (int, float))
        assert data["last_price"] > 0
        assert data["best_bid"] > 0
        assert data["best_ask"] > 0
        
        print(f"✓ BTC-EUR Ticker: price={data['last_price']}, bid={data['best_bid']}, ask={data['best_ask']}, spread={data['spread']}")

    def test_get_eth_eur_ticker(self, api_client):
        """Test GET /api/trading/pairs/ETH-EUR/ticker"""
        response = api_client.get(f"{BASE_URL}/api/trading/pairs/ETH-EUR/ticker")
        assert response.status_code == 200
        
        data = response.json()
        assert data["pair_id"] == "ETH-EUR"
        assert data["last_price"] > 0
        print(f"✓ ETH-EUR Ticker: price={data['last_price']}")


class TestOrderBook:
    """Order book endpoint tests"""
    
    def test_get_orderbook_btc_eur(self, api_client):
        """Test GET /api/trading/pairs/BTC-EUR/orderbook?depth=10"""
        response = api_client.get(f"{BASE_URL}/api/trading/pairs/BTC-EUR/orderbook?depth=10")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "pair_id" in data
        assert data["pair_id"] == "BTC-EUR"
        assert "bids" in data
        assert "asks" in data
        assert isinstance(data["bids"], list)
        assert isinstance(data["asks"], list)
        
        # Check bid/ask structure
        if data["bids"]:
            bid = data["bids"][0]
            assert "price" in bid
            assert "quantity" in bid
        
        if data["asks"]:
            ask = data["asks"][0]
            assert "price" in ask
            assert "quantity" in ask
        
        print(f"✓ BTC-EUR Order Book: {len(data['bids'])} bids, {len(data['asks'])} asks")

    def test_orderbook_depth_parameter(self, api_client):
        """Test order book depth parameter"""
        response = api_client.get(f"{BASE_URL}/api/trading/pairs/ETH-EUR/orderbook?depth=5")
        assert response.status_code == 200
        
        data = response.json()
        # Depth should limit results (synthetic data fills up to depth)
        assert len(data["bids"]) <= 5 or len(data["asks"]) <= 5
        print(f"✓ Order book depth parameter working")


class TestCandles:
    """Candle data endpoint tests"""
    
    def test_get_candles_btc_eur(self, api_client):
        """Test GET /api/trading/pairs/BTC-EUR/candles?interval=1h&limit=50"""
        response = api_client.get(f"{BASE_URL}/api/trading/pairs/BTC-EUR/candles?interval=1h&limit=50")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "pair_id" in data
        assert data["pair_id"] == "BTC-EUR"
        assert "interval" in data
        assert data["interval"] == "1h"
        assert "candles" in data
        assert isinstance(data["candles"], list)
        
        # Check candle structure (OHLCV)
        if data["candles"]:
            candle = data["candles"][0]
            assert "time" in candle
            assert "open" in candle
            assert "high" in candle
            assert "low" in candle
            assert "close" in candle
            assert "volume" in candle
            
            # Verify OHLC relationship
            assert candle["high"] >= candle["low"]
        
        print(f"✓ BTC-EUR Candles: {len(data['candles'])} candles with interval {data['interval']}")

    def test_candles_different_intervals(self, api_client):
        """Test different candle intervals"""
        intervals = ["1m", "5m", "15m", "1h", "4h", "1d"]
        for interval in intervals:
            response = api_client.get(f"{BASE_URL}/api/trading/pairs/BTC-EUR/candles?interval={interval}&limit=10")
            assert response.status_code == 200, f"Failed for interval {interval}"
        print(f"✓ All candle intervals working: {intervals}")


class TestOrderPlacement:
    """Order placement and management tests"""
    
    def test_place_market_buy_order(self, authenticated_client):
        """Test POST /api/trading/orders - market buy order for BTC-EUR"""
        order_data = {
            "pair_id": "BTC-EUR",
            "side": "buy",
            "order_type": "market",
            "quantity": 0.001
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/trading/orders", json=order_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "order" in data
        assert "message" in data
        
        order = data["order"]
        assert order["pair_id"] == "BTC-EUR"
        assert order["side"] == "buy"
        assert order["order_type"] == "market"
        assert order["quantity"] == 0.001
        # Market orders should fill immediately via market maker
        assert order["status"] == "filled"
        
        print(f"✓ Market BUY order placed: {data['message']}")

    def test_place_limit_sell_order(self, authenticated_client):
        """Test POST /api/trading/orders - limit sell order for ETH-EUR"""
        order_data = {
            "pair_id": "ETH-EUR",
            "side": "sell",
            "order_type": "limit",
            "quantity": 0.01,
            "price": 2000
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/trading/orders", json=order_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        order = data["order"]
        assert order["pair_id"] == "ETH-EUR"
        assert order["side"] == "sell"
        assert order["order_type"] == "limit"
        assert order["price"] == 2000
        # Limit order should be open (price too high to match immediately)
        assert order["status"] == "open"
        
        print(f"✓ Limit SELL order placed: {data['message']}, order_id={order['id']}")
        return order["id"]

    def test_get_my_orders(self, authenticated_client):
        """Test GET /api/trading/orders/my"""
        response = authenticated_client.get(f"{BASE_URL}/api/trading/orders/my")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "orders" in data
        assert "total" in data
        assert isinstance(data["orders"], list)
        
        if data["orders"]:
            order = data["orders"][0]
            assert "id" in order
            assert "pair_id" in order
            assert "side" in order
            assert "status" in order
        
        print(f"✓ My Orders: {data['total']} orders returned")
        return data["orders"]

    def test_cancel_open_limit_order(self, authenticated_client):
        """Test POST /api/trading/orders/cancel"""
        # First place a limit order to cancel
        order_data = {
            "pair_id": "SOL-EUR",
            "side": "sell",
            "order_type": "limit",
            "quantity": 0.1,
            "price": 200  # High price to remain open
        }
        
        create_response = authenticated_client.post(f"{BASE_URL}/api/trading/orders", json=order_data)
        assert create_response.status_code == 200
        
        order_id = create_response.json()["order"]["id"]
        
        # Now cancel it
        cancel_response = authenticated_client.post(
            f"{BASE_URL}/api/trading/orders/cancel",
            json={"order_id": order_id}
        )
        assert cancel_response.status_code == 200, f"Expected 200, got {cancel_response.status_code}: {cancel_response.text}"
        
        data = cancel_response.json()
        assert data["message"] == "Order cancelled"
        assert data["order_id"] == order_id
        
        print(f"✓ Order cancelled successfully: {order_id}")


class TestRecentTrades:
    """Recent trades endpoint tests"""
    
    def test_get_recent_trades(self, api_client):
        """Test GET /api/trading/trades/BTC-EUR"""
        response = api_client.get(f"{BASE_URL}/api/trading/trades/BTC-EUR")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "trades" in data
        assert "pair_id" in data
        assert data["pair_id"] == "BTC-EUR"
        assert isinstance(data["trades"], list)
        
        if data["trades"]:
            trade = data["trades"][0]
            assert "price" in trade
            assert "quantity" in trade
            assert "taker_side" in trade
        
        print(f"✓ Recent trades BTC-EUR: {len(data['trades'])} trades")


class TestPublicAPI:
    """Public API endpoint tests (no auth required)"""
    
    def test_public_api_docs(self, api_client):
        """Test GET /api/public/v1/docs"""
        response = api_client.get(f"{BASE_URL}/api/public/v1/docs")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "name" in data
        assert "version" in data
        assert "endpoints" in data
        
        # Should have 7 endpoints
        assert len(data["endpoints"]) == 7, f"Expected 7 endpoints, got {len(data['endpoints'])}"
        
        # Verify rate limits
        assert "rate_limits" in data
        
        print(f"✓ Public API Docs: {len(data['endpoints'])} endpoints documented")

    def test_public_market_coins(self, api_client):
        """Test GET /api/public/v1/market/coins"""
        response = api_client.get(f"{BASE_URL}/api/public/v1/market/coins")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "coins" in data
        assert len(data["coins"]) > 0
        
        print(f"✓ Public market coins: {len(data['coins'])} coins returned")

    def test_public_trading_pairs(self, api_client):
        """Test GET /api/public/v1/pairs"""
        response = api_client.get(f"{BASE_URL}/api/public/v1/pairs")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "pairs" in data
        assert "total" in data
        assert data["total"] >= 15
        
        print(f"✓ Public trading pairs: {data['total']} pairs returned")

    def test_public_ticker(self, api_client):
        """Test GET /api/public/v1/market/ticker/BTC-EUR"""
        response = api_client.get(f"{BASE_URL}/api/public/v1/market/ticker/BTC-EUR")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "pair_id" in data
        assert data["pair_id"] == "BTC-EUR"
        assert "last_price" in data
        assert "best_bid" in data
        assert "best_ask" in data
        
        print(f"✓ Public ticker BTC-EUR: price={data['last_price']}")

    def test_public_orderbook(self, api_client):
        """Test GET /api/public/v1/market/orderbook/BTC-EUR"""
        response = api_client.get(f"{BASE_URL}/api/public/v1/market/orderbook/BTC-EUR")
        assert response.status_code == 200
        
        data = response.json()
        assert "bids" in data
        assert "asks" in data
        print(f"✓ Public orderbook working")

    def test_public_candles(self, api_client):
        """Test GET /api/public/v1/market/candles/BTC-EUR"""
        response = api_client.get(f"{BASE_URL}/api/public/v1/market/candles/BTC-EUR")
        assert response.status_code == 200
        
        data = response.json()
        assert "candles" in data
        print(f"✓ Public candles: {len(data['candles'])} candles")

    def test_public_recent_trades(self, api_client):
        """Test GET /api/public/v1/market/trades/BTC-EUR"""
        response = api_client.get(f"{BASE_URL}/api/public/v1/market/trades/BTC-EUR")
        assert response.status_code == 200
        
        data = response.json()
        assert "trades" in data
        print(f"✓ Public trades: {len(data['trades'])} trades")


class TestEdgeCases:
    """Edge case and validation tests"""
    
    def test_invalid_pair_ticker(self, api_client):
        """Test ticker with invalid pair"""
        response = api_client.get(f"{BASE_URL}/api/trading/pairs/INVALID-PAIR/ticker")
        # Should return 200 with ref_price fallback or 404
        assert response.status_code in [200, 404]
        print(f"✓ Invalid pair handled correctly (status: {response.status_code})")

    def test_limit_order_without_price(self, authenticated_client):
        """Test limit order without price returns 400"""
        order_data = {
            "pair_id": "BTC-EUR",
            "side": "buy",
            "order_type": "limit",
            "quantity": 0.001
            # Missing price for limit order
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/trading/orders", json=order_data)
        assert response.status_code == 400 or response.status_code == 422, f"Expected 400/422, got {response.status_code}"
        print(f"✓ Limit order without price rejected correctly")

    def test_order_below_min_quantity(self, authenticated_client):
        """Test order below minimum quantity"""
        order_data = {
            "pair_id": "BTC-EUR",
            "side": "buy",
            "order_type": "market",
            "quantity": 0.00001  # Below min_qty of 0.0001
        }
        
        response = authenticated_client.post(f"{BASE_URL}/api/trading/orders", json=order_data)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print(f"✓ Below min quantity order rejected correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
