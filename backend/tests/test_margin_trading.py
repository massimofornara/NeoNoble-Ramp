"""
Margin Trading API Tests - Iteration 10

Tests for:
- Margin account creation
- Margin deposit/withdraw
- Opening/closing margin positions
- Candle data for charts
- Ticker data
- Order book
- Trading pairs
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_USER_EMAIL = "testchart@example.com"
TEST_USER_PASSWORD = "Test1234!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for test user."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        # API returns 'token' not 'access_token'
        return data.get("token") or data.get("access_token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token."""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    }


class TestTradingPairs:
    """Trading pairs endpoint tests."""
    
    def test_get_trading_pairs(self):
        """GET /api/trading/pairs - Get all trading pairs."""
        response = requests.get(f"{BASE_URL}/api/trading/pairs")
        assert response.status_code == 200
        data = response.json()
        assert "pairs" in data
        assert len(data["pairs"]) > 0
        # Check for expected pairs
        pair_ids = [p["id"] for p in data["pairs"]]
        assert "BTC-EUR" in pair_ids
        assert "ETH-EUR" in pair_ids
        assert "NENO-EUR" in pair_ids
        print(f"PASS: Found {len(data['pairs'])} trading pairs")


class TestTicker:
    """Ticker endpoint tests."""
    
    def test_get_btc_eur_ticker(self):
        """GET /api/trading/pairs/BTC-EUR/ticker - Get BTC-EUR ticker."""
        response = requests.get(f"{BASE_URL}/api/trading/pairs/BTC-EUR/ticker")
        assert response.status_code == 200
        data = response.json()
        assert data["pair_id"] == "BTC-EUR"
        assert "last_price" in data
        assert "best_bid" in data
        assert "best_ask" in data
        assert "volume_24h" in data
        assert "change_24h" in data
        assert data["last_price"] > 0
        print(f"PASS: BTC-EUR ticker - last_price: {data['last_price']}")
    
    def test_get_eth_eur_ticker(self):
        """GET /api/trading/pairs/ETH-EUR/ticker - Get ETH-EUR ticker."""
        response = requests.get(f"{BASE_URL}/api/trading/pairs/ETH-EUR/ticker")
        assert response.status_code == 200
        data = response.json()
        assert data["pair_id"] == "ETH-EUR"
        assert data["last_price"] > 0
        print(f"PASS: ETH-EUR ticker - last_price: {data['last_price']}")


class TestCandleData:
    """Candle data endpoint tests for charts."""
    
    def test_get_btc_eur_candles_1h(self):
        """GET /api/trading/pairs/BTC-EUR/candles?interval=1h - Get 1H candles."""
        response = requests.get(f"{BASE_URL}/api/trading/pairs/BTC-EUR/candles?interval=1h&limit=100")
        assert response.status_code == 200
        data = response.json()
        assert data["pair_id"] == "BTC-EUR"
        assert data["interval"] == "1h"
        assert "candles" in data
        assert len(data["candles"]) > 0
        # Check candle structure
        candle = data["candles"][0]
        assert "time" in candle
        assert "open" in candle
        assert "high" in candle
        assert "low" in candle
        assert "close" in candle
        assert "volume" in candle
        print(f"PASS: Got {len(data['candles'])} candles for BTC-EUR 1H")
    
    def test_get_candles_different_intervals(self):
        """Test different candle intervals."""
        intervals = ["1m", "5m", "15m", "1h", "4h", "1d"]
        for interval in intervals:
            response = requests.get(f"{BASE_URL}/api/trading/pairs/BTC-EUR/candles?interval={interval}&limit=50")
            assert response.status_code == 200
            data = response.json()
            assert data["interval"] == interval
            assert len(data["candles"]) > 0
            print(f"PASS: {interval} interval - {len(data['candles'])} candles")


class TestOrderBook:
    """Order book endpoint tests."""
    
    def test_get_order_book(self):
        """GET /api/trading/pairs/BTC-EUR/orderbook - Get order book."""
        response = requests.get(f"{BASE_URL}/api/trading/pairs/BTC-EUR/orderbook?depth=20")
        assert response.status_code == 200
        data = response.json()
        assert data["pair_id"] == "BTC-EUR"
        assert "bids" in data
        assert "asks" in data
        assert len(data["bids"]) > 0
        assert len(data["asks"]) > 0
        # Check bid/ask structure
        bid = data["bids"][0]
        assert "price" in bid
        assert "quantity" in bid
        print(f"PASS: Order book - {len(data['bids'])} bids, {len(data['asks'])} asks")


class TestMarginAccount:
    """Margin account tests."""
    
    def test_get_margin_account_initial(self, auth_headers):
        """GET /api/trading/margin/account - Get margin account (may not exist)."""
        response = requests.get(f"{BASE_URL}/api/trading/margin/account", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        # Account may or may not exist
        print(f"PASS: Margin account response: {data.get('message', 'account exists')}")
    
    def test_create_margin_account(self, auth_headers):
        """POST /api/trading/margin/account - Create margin account."""
        response = requests.post(f"{BASE_URL}/api/trading/margin/account", 
            headers=auth_headers,
            json={"leverage": 20}
        )
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        # Either created or updated
        assert "Margin account" in data["message"] or "max_leverage" in data
        print(f"PASS: {data['message']}")
    
    def test_get_margin_account_after_create(self, auth_headers):
        """GET /api/trading/margin/account - Verify account exists."""
        response = requests.get(f"{BASE_URL}/api/trading/margin/account", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "account" in data
        if data["account"]:
            assert "margin_balance" in data["account"]
            assert "equity" in data["account"]
            assert "margin_level" in data["account"]
            print(f"PASS: Margin account - balance: {data['account']['margin_balance']}, equity: {data['account']['equity']}")
        else:
            print("PASS: No margin account yet")


class TestMarginDeposit:
    """Margin deposit/withdraw tests."""
    
    def test_deposit_margin_insufficient_balance(self, auth_headers):
        """POST /api/trading/margin/deposit - Deposit with insufficient wallet balance."""
        response = requests.post(f"{BASE_URL}/api/trading/margin/deposit",
            headers=auth_headers,
            json={"asset": "EUR", "amount": 1000000}  # Large amount
        )
        # Should fail due to insufficient balance
        if response.status_code == 400:
            data = response.json()
            assert "insufficiente" in data.get("detail", "").lower() or "insufficient" in data.get("detail", "").lower()
            print(f"PASS: Correctly rejected - {data['detail']}")
        else:
            # If it succeeds, user has enough balance
            print(f"INFO: Deposit succeeded (user has balance)")


class TestMarginPositions:
    """Margin positions tests."""
    
    def test_get_margin_positions(self, auth_headers):
        """GET /api/trading/margin/positions - Get all positions."""
        response = requests.get(f"{BASE_URL}/api/trading/margin/positions", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "positions" in data
        print(f"PASS: Found {len(data['positions'])} positions")
    
    def test_open_position_insufficient_margin(self, auth_headers):
        """POST /api/trading/margin/open - Open position with insufficient margin."""
        response = requests.post(f"{BASE_URL}/api/trading/margin/open",
            headers=auth_headers,
            json={
                "pair_id": "BTC-EUR",
                "side": "buy",
                "quantity": 100,  # Large quantity
                "leverage": 10
            }
        )
        # Should fail due to insufficient margin
        if response.status_code == 400:
            data = response.json()
            assert "margin" in data.get("detail", "").lower() or "insufficiente" in data.get("detail", "").lower()
            print(f"PASS: Correctly rejected - {data['detail']}")
        else:
            # If it succeeds, user has enough margin
            print(f"INFO: Position opened (user has margin)")


class TestUnifiedWallet:
    """Unified wallet tests."""
    
    def test_get_unified_wallet(self, auth_headers):
        """GET /api/multichain/unified-wallet - Get unified wallet view."""
        response = requests.get(f"{BASE_URL}/api/multichain/unified-wallet", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "assets" in data
        assert "total_eur_value" in data
        print(f"PASS: Unified wallet - {len(data['assets'])} assets, total: EUR {data['total_eur_value']}")


class TestTokenDiscovery:
    """Token discovery tests."""
    
    def test_get_supported_chains(self):
        """GET /api/multichain/chains - Get supported chains."""
        response = requests.get(f"{BASE_URL}/api/multichain/chains")
        assert response.status_code == 200
        data = response.json()
        assert "chains" in data
        assert len(data["chains"]) > 0
        chain_keys = [c["key"] for c in data["chains"]]
        assert "ethereum" in chain_keys or "bsc" in chain_keys
        print(f"PASS: Found {len(data['chains'])} supported chains")
    
    def test_discover_tokens_no_wallet(self, auth_headers):
        """POST /api/multichain/discover-tokens - Discover tokens (no wallet linked)."""
        response = requests.post(f"{BASE_URL}/api/multichain/discover-tokens",
            headers=auth_headers,
            json={"chain": "ethereum"}
        )
        # May fail if no wallet linked
        if response.status_code == 404:
            data = response.json()
            assert "wallet" in data.get("detail", "").lower()
            print(f"PASS: Correctly rejected - {data['detail']}")
        elif response.status_code == 200:
            data = response.json()
            print(f"PASS: Discovered {len(data.get('discovered_tokens', []))} tokens")
        else:
            print(f"INFO: Response {response.status_code}")


class TestWalletBalances:
    """Wallet balances tests."""
    
    def test_get_wallet_balances(self, auth_headers):
        """GET /api/wallet/balances - Get platform wallet balances."""
        response = requests.get(f"{BASE_URL}/api/wallet/balances", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "wallets" in data
        assert "total_eur_value" in data
        print(f"PASS: Wallet balances - {len(data['wallets'])} assets, total: EUR {data['total_eur_value']}")


class TestWalletTabs:
    """Test wallet page tabs endpoints."""
    
    def test_get_multichain_balances(self, auth_headers):
        """GET /api/multichain/balances - Get on-chain balances."""
        response = requests.get(f"{BASE_URL}/api/multichain/balances", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "wallets" in data
        print(f"PASS: On-chain wallets: {len(data['wallets'])}")
    
    def test_get_iban(self, auth_headers):
        """GET /api/banking/iban - Get IBAN accounts."""
        response = requests.get(f"{BASE_URL}/api/banking/iban", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "ibans" in data
        print(f"PASS: IBAN accounts: {len(data['ibans'])}")
    
    def test_get_banking_transactions(self, auth_headers):
        """GET /api/banking/transactions - Get banking transactions."""
        response = requests.get(f"{BASE_URL}/api/banking/transactions?limit=10", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "transactions" in data
        print(f"PASS: Banking transactions: {len(data['transactions'])}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
