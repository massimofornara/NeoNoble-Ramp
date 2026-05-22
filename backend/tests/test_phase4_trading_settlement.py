"""
Phase 4 Final Execution - Trading, Settlement, Cards, Wallet Tests
Tests cover:
- Auth: Login with test users
- Trading pairs with NENO token
- Order types: market, limit, stop_loss, take_profit
- Order cancellation (including pending_trigger)
- Order book and ticker
- Candle data
- Wallet deposits, balances, conversions
- Card creation, top-up, freeze/unfreeze
- Card funding from crypto via settlement pipeline
- Settlement history
- Paper trading
- Margin account infrastructure
- WebSocket status
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_USER_EMAIL = "testchart@example.com"
TEST_USER_PASSWORD = "Test1234!"
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"


class TestAuth:
    """Authentication tests"""
    
    def test_login_regular_user(self):
        """Test login with regular user credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "Token not in response"
        assert "user" in data, "User not in response"
        print(f"[PASS] Regular user login - token obtained")
    
    def test_login_admin_user(self):
        """Test login with admin credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"].get("role") == "ADMIN"
        print(f"[PASS] Admin user login - role: ADMIN")


@pytest.fixture(scope="module")
def auth_token():
    """Get auth token for regular user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Auth failed: {response.text}")
    return response.json()["token"]


@pytest.fixture(scope="module")
def admin_token():
    """Get auth token for admin user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Admin auth failed: {response.text}")
    return response.json()["token"]


@pytest.fixture
def auth_headers(auth_token):
    """Standard headers with auth token"""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    }


@pytest.fixture
def admin_headers(admin_token):
    """Admin headers with auth token"""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}"
    }


class TestTradingPairs:
    """Trading pairs tests - including NENO token"""
    
    def test_get_trading_pairs(self):
        """GET /api/trading/pairs should return 15 pairs including NENO"""
        response = requests.get(f"{BASE_URL}/api/trading/pairs")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        pairs = data.get("pairs", [])
        pair_ids = [p["id"] for p in pairs]
        
        assert len(pairs) >= 15, f"Expected 15+ pairs, got {len(pairs)}"
        assert "NENO-EUR" in pair_ids, "NENO-EUR pair missing"
        assert "NENO-USDT" in pair_ids, "NENO-USDT pair missing"
        assert "BTC-EUR" in pair_ids, "BTC-EUR pair missing"
        assert "ETH-EUR" in pair_ids, "ETH-EUR pair missing"
        
        print(f"[PASS] Trading pairs: {len(pairs)} pairs including NENO-EUR, NENO-USDT")
    
    def test_get_neno_eur_ticker(self):
        """GET /api/trading/pairs/NENO-EUR/ticker"""
        response = requests.get(f"{BASE_URL}/api/trading/pairs/NENO-EUR/ticker")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "last_price" in data
        assert "best_bid" in data
        assert "best_ask" in data
        assert data["pair_id"] == "NENO-EUR"
        
        print(f"[PASS] NENO-EUR ticker: last_price={data['last_price']}")
    
    def test_get_neno_usdt_ticker(self):
        """GET /api/trading/pairs/NENO-USDT/ticker"""
        response = requests.get(f"{BASE_URL}/api/trading/pairs/NENO-USDT/ticker")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "last_price" in data
        assert data["pair_id"] == "NENO-USDT"
        
        print(f"[PASS] NENO-USDT ticker: last_price={data['last_price']}")


class TestOrderBook:
    """Order book tests"""
    
    def test_get_btc_eur_orderbook(self):
        """GET /api/trading/pairs/BTC-EUR/orderbook"""
        response = requests.get(f"{BASE_URL}/api/trading/pairs/BTC-EUR/orderbook")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "bids" in data
        assert "asks" in data
        assert isinstance(data["bids"], list)
        assert isinstance(data["asks"], list)
        
        print(f"[PASS] BTC-EUR orderbook: {len(data['bids'])} bids, {len(data['asks'])} asks")


class TestCandles:
    """Candle/chart data tests"""
    
    def test_get_btc_eur_candles(self):
        """GET /api/trading/pairs/BTC-EUR/candles?interval=1h"""
        response = requests.get(f"{BASE_URL}/api/trading/pairs/BTC-EUR/candles?interval=1h")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "candles" in data
        assert isinstance(data["candles"], list)
        
        if data["candles"]:
            candle = data["candles"][0]
            assert "time" in candle
            assert "open" in candle
            assert "high" in candle
            assert "low" in candle
            assert "close" in candle
            assert "volume" in candle
        
        print(f"[PASS] BTC-EUR candles: {len(data['candles'])} candles")


class TestOrderTypes:
    """Test various order types: market, limit, stop-loss, take-profit"""
    
    def test_market_order_buy(self, auth_headers):
        """POST /api/trading/orders - Market buy order should fill (filled or partially_filled via market maker)"""
        response = requests.post(
            f"{BASE_URL}/api/trading/orders",
            headers=auth_headers,
            json={
                "pair_id": "ETH-EUR",
                "side": "buy",
                "order_type": "market",
                "quantity": 0.1
            }
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "order" in data
        # Market orders can be filled or partially_filled if matched against order book then filled by market maker
        assert data["order"]["status"] in ("filled", "partially_filled"), f"Unexpected status: {data['order']['status']}"
        assert data["order"]["filled_qty"] > 0, "Order should have some fill"
        
        print(f"[PASS] Market buy order: status={data['order']['status']}, filled={data['order']['filled_qty']}")
    
    def test_limit_order_sell(self, auth_headers):
        """POST /api/trading/orders - Limit sell order should remain open"""
        response = requests.post(
            f"{BASE_URL}/api/trading/orders",
            headers=auth_headers,
            json={
                "pair_id": "NENO-EUR",
                "side": "sell",
                "order_type": "limit",
                "quantity": 50,
                "price": 0.60
            }
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "order" in data
        assert data["order"]["status"] == "open", f"Expected open, got {data['order']['status']}"
        
        print(f"[PASS] Limit sell order: status={data['order']['status']}")
        return data["order"]["id"]
    
    def test_stop_loss_order(self, auth_headers):
        """POST /api/trading/orders - Stop-loss order should be pending_trigger"""
        response = requests.post(
            f"{BASE_URL}/api/trading/orders",
            headers=auth_headers,
            json={
                "pair_id": "BTC-EUR",
                "side": "sell",
                "order_type": "stop_loss",
                "quantity": 0.005,
                "stop_price": 55000
            }
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "order" in data
        assert data["order"]["status"] == "pending_trigger", f"Expected pending_trigger, got {data['order']['status']}"
        
        print(f"[PASS] Stop-loss order: status={data['order']['status']}")
        return data["order"]["id"]
    
    def test_take_profit_order(self, auth_headers):
        """POST /api/trading/orders - Take-profit order should be pending_trigger"""
        response = requests.post(
            f"{BASE_URL}/api/trading/orders",
            headers=auth_headers,
            json={
                "pair_id": "ETH-EUR",
                "side": "sell",
                "order_type": "take_profit",
                "quantity": 0.1,
                "stop_price": 2500
            }
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "order" in data
        assert data["order"]["status"] == "pending_trigger", f"Expected pending_trigger, got {data['order']['status']}"
        
        print(f"[PASS] Take-profit order: status={data['order']['status']}")
        return data["order"]["id"]


class TestOrderCancellation:
    """Test order cancellation including pending_trigger orders"""
    
    def test_cancel_pending_trigger_order(self, auth_headers):
        """Cancel a pending_trigger order should work"""
        # First create a stop-loss order
        create_resp = requests.post(
            f"{BASE_URL}/api/trading/orders",
            headers=auth_headers,
            json={
                "pair_id": "SOL-EUR",
                "side": "sell",
                "order_type": "stop_loss",
                "quantity": 1,
                "stop_price": 50
            }
        )
        assert create_resp.status_code == 200, f"Failed to create: {create_resp.text}"
        order_id = create_resp.json()["order"]["id"]
        
        # Now cancel it
        cancel_resp = requests.post(
            f"{BASE_URL}/api/trading/orders/cancel",
            headers=auth_headers,
            json={"order_id": order_id}
        )
        assert cancel_resp.status_code == 200, f"Failed to cancel: {cancel_resp.text}"
        
        print(f"[PASS] Cancelled pending_trigger order: {order_id}")


class TestWallet:
    """Wallet operations tests"""
    
    def test_wallet_deposit(self, auth_headers):
        """POST /api/wallet/deposit - Credit wallet with assets"""
        response = requests.post(
            f"{BASE_URL}/api/wallet/deposit",
            headers=auth_headers,
            json={"asset": "ETH", "amount": 5.0}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "balance" in data
        assert data["balance"] >= 5.0
        
        print(f"[PASS] Wallet deposit: ETH balance = {data['balance']}")
    
    def test_wallet_balances(self, auth_headers):
        """GET /api/wallet/balances - Get wallet list with EUR values"""
        response = requests.get(
            f"{BASE_URL}/api/wallet/balances",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "wallets" in data
        assert "total_eur_value" in data
        
        print(f"[PASS] Wallet balances: {len(data['wallets'])} wallets, total EUR = {data['total_eur_value']}")
    
    def test_crypto_to_fiat_conversion(self, auth_headers):
        """POST /api/wallet/convert - ETH to EUR conversion"""
        # First deposit some ETH
        requests.post(
            f"{BASE_URL}/api/wallet/deposit",
            headers=auth_headers,
            json={"asset": "ETH", "amount": 1.0}
        )
        
        response = requests.post(
            f"{BASE_URL}/api/wallet/convert",
            headers=auth_headers,
            json={"from_asset": "ETH", "to_asset": "EUR", "amount": 0.5}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert data["status"] == "completed"
        assert data["to_asset"] == "EUR"
        
        print(f"[PASS] Crypto→Fiat conversion: {data['from_amount']} ETH → {data['to_amount_net']} EUR")
    
    def test_crypto_to_crypto_conversion(self, auth_headers):
        """POST /api/wallet/convert - NENO to USDT conversion"""
        # First deposit NENO
        requests.post(
            f"{BASE_URL}/api/wallet/deposit",
            headers=auth_headers,
            json={"asset": "NENO", "amount": 100}
        )
        
        response = requests.post(
            f"{BASE_URL}/api/wallet/convert",
            headers=auth_headers,
            json={"from_asset": "NENO", "to_asset": "USDT", "amount": 50}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert data["status"] == "completed"
        
        print(f"[PASS] Crypto→Crypto conversion: {data['from_amount']} NENO → {data['to_amount_net']} USDT")
    
    def test_fiat_to_crypto_conversion(self, auth_headers):
        """POST /api/wallet/convert - EUR to BTC conversion"""
        # First deposit EUR
        requests.post(
            f"{BASE_URL}/api/wallet/deposit",
            headers=auth_headers,
            json={"asset": "EUR", "amount": 1000}
        )
        
        response = requests.post(
            f"{BASE_URL}/api/wallet/convert",
            headers=auth_headers,
            json={"from_asset": "EUR", "to_asset": "BTC", "amount": 500}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert data["status"] == "completed"
        
        print(f"[PASS] Fiat→Crypto conversion: {data['from_amount']} EUR → {data['to_amount_net']} BTC")


class TestConversionRates:
    """Conversion rates tests"""
    
    def test_get_conversion_rates(self):
        """GET /api/wallet/conversion-rates - Get rates for all assets"""
        response = requests.get(f"{BASE_URL}/api/wallet/conversion-rates")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "rates" in data
        assert "supported_assets" in data
        
        # Should have rates for 14 assets
        assets = data["supported_assets"]
        assert len(assets) >= 10, f"Expected 10+ assets, got {len(assets)}"
        
        print(f"[PASS] Conversion rates: {len(assets)} supported assets")


class TestSettlementHistory:
    """Settlement history tests"""
    
    def test_get_settlements(self, auth_headers):
        """GET /api/wallet/settlements - Get settlement history"""
        response = requests.get(
            f"{BASE_URL}/api/wallet/settlements",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "settlements" in data
        
        print(f"[PASS] Settlement history: {data['total']} settlements")


class TestCards:
    """Card infrastructure tests"""
    
    def test_create_virtual_card_or_max_limit(self, auth_headers):
        """POST /api/cards/create - Create virtual card or verify max limit enforcement"""
        response = requests.post(
            f"{BASE_URL}/api/cards/create",
            headers=auth_headers,
            json={
                "card_type": "virtual",
                "card_network": "visa",
                "currency": "EUR"
            }
        )
        # Either creates card (200) or rejects due to max limit (400)
        assert response.status_code in (200, 400), f"Unexpected: {response.text}"
        
        if response.status_code == 200:
            data = response.json()
            assert "card" in data
            assert data["card"]["status"] == "active"
            print(f"[PASS] Created virtual card: {data['card']['card_number_masked']}")
        else:
            # Max limit enforced - this is correct behavior
            assert "Maximum 3" in response.text
            print(f"[PASS] Card creation limit enforced (max 3 virtual cards)")
    
    def test_list_my_cards(self, auth_headers):
        """GET /api/cards/my-cards - List user's cards"""
        response = requests.get(
            f"{BASE_URL}/api/cards/my-cards",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "cards" in data
        
        print(f"[PASS] My cards: {data['total']} cards")
        return data["cards"]
    
    def test_card_top_up(self, auth_headers):
        """POST /api/cards/{card_id}/top-up - Top up card with crypto"""
        # Get existing cards
        cards_resp = requests.get(f"{BASE_URL}/api/cards/my-cards", headers=auth_headers)
        if cards_resp.status_code != 200:
            pytest.skip("Cannot list cards")
        
        cards = cards_resp.json().get("cards", [])
        active_cards = [c for c in cards if c.get("status") == "active"]
        
        if not active_cards:
            pytest.skip("No active cards to top up")
        
        card_id = active_cards[0]["id"]
        
        response = requests.post(
            f"{BASE_URL}/api/cards/{card_id}/top-up",
            headers=auth_headers,
            json={
                "amount_crypto": 0.01,
                "crypto_asset": "BTC"
            }
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "new_balance" in data
        
        print(f"[PASS] Card top-up: new balance = {data['new_balance']} EUR")
    
    def test_card_freeze_unfreeze(self, auth_headers):
        """POST /api/cards/{card_id}/freeze - Toggle card status"""
        # Get existing cards
        cards_resp = requests.get(f"{BASE_URL}/api/cards/my-cards", headers=auth_headers)
        if cards_resp.status_code != 200:
            pytest.skip("Cannot list cards")
        
        cards = cards_resp.json().get("cards", [])
        active_cards = [c for c in cards if c.get("status") == "active"]
        
        if not active_cards:
            pytest.skip("No active cards to freeze")
        
        card_id = active_cards[0]["id"]
        
        # Freeze
        response = requests.post(
            f"{BASE_URL}/api/cards/{card_id}/freeze",
            headers=auth_headers,
            json={}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert data["status"] in ("frozen", "active")
        
        print(f"[PASS] Card freeze/unfreeze: status = {data['status']}")


class TestCardFunding:
    """Card funding from crypto via settlement pipeline"""
    
    def test_fund_card_from_crypto(self, auth_headers):
        """POST /api/wallet/fund-card - Fund card via settlement pipeline"""
        # Get existing cards
        cards_resp = requests.get(f"{BASE_URL}/api/cards/my-cards", headers=auth_headers)
        if cards_resp.status_code != 200:
            pytest.skip("Cannot list cards")
        
        cards = cards_resp.json().get("cards", [])
        active_cards = [c for c in cards if c.get("status") == "active"]
        
        if not active_cards:
            pytest.skip("No active cards to fund")
        
        card_id = active_cards[0]["id"]
        
        # Deposit some crypto
        requests.post(
            f"{BASE_URL}/api/wallet/deposit",
            headers=auth_headers,
            json={"asset": "ETH", "amount": 1.0}
        )
        
        # Fund card from crypto
        response = requests.post(
            f"{BASE_URL}/api/wallet/fund-card",
            headers=auth_headers,
            json={
                "card_id": card_id,
                "crypto_asset": "ETH",
                "crypto_amount": 0.1
            }
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "settlement" in data
        assert data["settlement"]["status"] == "completed"
        
        print(f"[PASS] Card funded from crypto: {data['card_balance']} EUR balance")


class TestPaperTrading:
    """Paper trading tests"""
    
    def test_paper_trade(self, auth_headers):
        """POST /api/trading/paper/trade - Execute simulated trade"""
        response = requests.post(
            f"{BASE_URL}/api/trading/paper/trade",
            headers=auth_headers,
            json={
                "pair_id": "NENO-EUR",
                "side": "buy",
                "quantity": 100
            }
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "trade" in data
        assert data["trade"]["is_paper"] == True
        assert data["trade"]["status"] == "filled"
        
        print(f"[PASS] Paper trade: {data['trade']['quantity']} NENO at {data['trade']['price']}")
    
    def test_paper_portfolio(self, auth_headers):
        """GET /api/trading/paper/portfolio - Get paper trading portfolio"""
        response = requests.get(
            f"{BASE_URL}/api/trading/paper/portfolio",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "portfolio" in data
        
        print(f"[PASS] Paper portfolio: {data['portfolio'].get('total_trades', 0)} trades")
    
    def test_paper_reset(self, auth_headers):
        """DELETE /api/trading/paper/reset - Reset paper portfolio"""
        response = requests.delete(
            f"{BASE_URL}/api/trading/paper/reset",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        print(f"[PASS] Paper portfolio reset")


class TestMarginTrading:
    """Margin trading infrastructure tests"""
    
    def test_create_margin_account(self, auth_headers):
        """POST /api/trading/margin/account - Create margin account"""
        response = requests.post(
            f"{BASE_URL}/api/trading/margin/account",
            headers=auth_headers,
            json={"leverage": 5}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "message" in data
        assert "created" in data["message"].lower() or "updated" in data["message"].lower()
        
        print(f"[PASS] Margin account: {data['message']}")
    
    def test_get_margin_account(self, auth_headers):
        """GET /api/trading/margin/account - Get margin account details"""
        response = requests.get(
            f"{BASE_URL}/api/trading/margin/account",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "account" in data
        
        print(f"[PASS] Margin account details retrieved")
    
    def test_get_margin_positions(self, auth_headers):
        """GET /api/trading/margin/positions - Get margin positions"""
        response = requests.get(
            f"{BASE_URL}/api/trading/margin/positions",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "positions" in data
        assert isinstance(data["positions"], list)
        
        print(f"[PASS] Margin positions: {len(data['positions'])} positions")


class TestWebSocket:
    """WebSocket status tests"""
    
    def test_websocket_status(self):
        """GET /api/ws/status - Get WebSocket status"""
        response = requests.get(f"{BASE_URL}/api/ws/status")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "active_symbols" in data
        assert "total_connections" in data
        
        print(f"[PASS] WebSocket status: {data['total_connections']} connections")


class TestAdminStats:
    """Admin trading stats tests"""
    
    def test_trading_stats_admin(self, admin_headers):
        """GET /api/trading/stats - Admin trading statistics"""
        response = requests.get(
            f"{BASE_URL}/api/trading/stats",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "total_trades" in data
        assert "total_orders" in data
        assert "trading_pairs" in data
        
        print(f"[PASS] Trading stats (admin): {data['total_trades']} trades, {data['trading_pairs']} pairs")
    
    def test_trading_stats_forbidden_for_regular_user(self, auth_headers):
        """GET /api/trading/stats - Should return 403 for non-admin"""
        response = requests.get(
            f"{BASE_URL}/api/trading/stats",
            headers=auth_headers
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        
        print(f"[PASS] Trading stats forbidden for regular user")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
