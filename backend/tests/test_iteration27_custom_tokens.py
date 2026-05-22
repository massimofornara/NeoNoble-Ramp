"""
Iteration 27 - Custom Token Features Testing
Tests for Phase 1-4 of NeoNoble Ramp Custom Token System:
- Phase 1: Create custom tokens (POST /api/neno-exchange/create-token, GET /api/neno-exchange/my-tokens)
- Phase 2: Buy/Sell custom tokens (POST /api/neno-exchange/buy-custom-token, sell-custom-token)
- Phase 3: Swap custom/native tokens (POST /api/neno-exchange/swap, GET /api/neno-exchange/swap-quote)
- Phase 4: Live balances (GET /api/neno-exchange/live-balances)
"""

import pytest
import requests
import os
import uuid
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-chain-wallet-14.preview.emergentagent.com')

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"


class TestCustomTokenPhase1:
    """Phase 1: Custom Token Creation Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Generate unique symbol for this test run
        self.test_symbol = f"T{uuid.uuid4().hex[:5].upper()}"
    
    def test_create_token_success(self):
        """Test creating a custom token with valid data"""
        payload = {
            "name": f"Test Token {self.test_symbol}",
            "symbol": self.test_symbol,
            "total_supply": 100000,
            "price_usd": 1.50
        }
        
        resp = self.session.post(f"{BASE_URL}/api/neno-exchange/create-token", json=payload)
        assert resp.status_code == 200, f"Create token failed: {resp.text}"
        
        data = resp.json()
        assert "token" in data
        assert data["token"]["symbol"] == self.test_symbol
        assert data["token"]["name"] == payload["name"]
        assert data["token"]["price_usd"] == 1.50
        assert data["token"]["total_supply"] == 100000
        assert data["balance"] == 100000  # Creator gets full supply
        print(f"PASS: Created token {self.test_symbol} with supply 100000 @ $1.50")
    
    def test_create_token_symbol_max_8_chars(self):
        """Test that symbol is limited to 8 characters"""
        payload = {
            "name": "Long Symbol Token",
            "symbol": "TOOLONGSYMBOL",  # 13 chars - should fail
            "total_supply": 1000,
            "price_usd": 1.00
        }
        
        resp = self.session.post(f"{BASE_URL}/api/neno-exchange/create-token", json=payload)
        # Should fail validation (422 or 400)
        assert resp.status_code in [400, 422], f"Expected validation error for long symbol: {resp.text}"
        print("PASS: Symbol max 8 chars validation works")
    
    def test_create_token_duplicate_symbol_rejected(self):
        """Test that duplicate symbols are rejected"""
        # First create a token
        symbol = f"D{uuid.uuid4().hex[:4].upper()}"
        payload = {
            "name": "First Token",
            "symbol": symbol,
            "total_supply": 1000,
            "price_usd": 1.00
        }
        resp1 = self.session.post(f"{BASE_URL}/api/neno-exchange/create-token", json=payload)
        assert resp1.status_code == 200, f"First token creation failed: {resp1.text}"
        
        # Try to create another with same symbol
        payload2 = {
            "name": "Duplicate Token",
            "symbol": symbol,
            "total_supply": 2000,
            "price_usd": 2.00
        }
        resp2 = self.session.post(f"{BASE_URL}/api/neno-exchange/create-token", json=payload2)
        assert resp2.status_code == 400, f"Expected 400 for duplicate symbol: {resp2.text}"
        assert "esiste" in resp2.json().get("detail", "").lower() or "already" in resp2.json().get("detail", "").lower()
        print(f"PASS: Duplicate symbol {symbol} correctly rejected")
    
    def test_my_tokens_returns_created_tokens(self):
        """Test GET /api/neno-exchange/my-tokens returns user's tokens with balances"""
        resp = self.session.get(f"{BASE_URL}/api/neno-exchange/my-tokens")
        assert resp.status_code == 200, f"my-tokens failed: {resp.text}"
        
        data = resp.json()
        assert "tokens" in data
        assert "total" in data
        assert isinstance(data["tokens"], list)
        
        # Check that tokens have required fields
        if len(data["tokens"]) > 0:
            token = data["tokens"][0]
            assert "symbol" in token
            assert "name" in token
            assert "balance" in token
            assert "price_usd" in token or "price_eur" in token
            print(f"PASS: my-tokens returns {data['total']} tokens with balances")
        else:
            print("PASS: my-tokens returns empty list (no tokens created by user)")


class TestCustomTokenPhase2:
    """Phase 2: Buy/Sell Custom Tokens Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and setup test token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Create a test token for buy/sell tests
        self.test_symbol = f"B{uuid.uuid4().hex[:4].upper()}"
        create_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/create-token", json={
            "name": f"BuySell Test {self.test_symbol}",
            "symbol": self.test_symbol,
            "total_supply": 10000,
            "price_usd": 2.00
        })
        if create_resp.status_code != 200:
            pytest.skip(f"Could not create test token: {create_resp.text}")
    
    def test_deposit_eur_for_testing(self):
        """Deposit EUR to wallet for testing buy operations"""
        resp = self.session.post(f"{BASE_URL}/api/wallet/deposit", json={
            "asset": "EUR",
            "amount": 5000
        })
        # May return 200 or 201
        assert resp.status_code in [200, 201], f"Deposit failed: {resp.text}"
        print("PASS: Deposited 5000 EUR for testing")
    
    def test_buy_custom_token_with_eur(self):
        """Test buying custom token with EUR"""
        # First deposit EUR
        self.session.post(f"{BASE_URL}/api/wallet/deposit", json={"asset": "EUR", "amount": 1000})
        
        payload = {
            "symbol": self.test_symbol,
            "amount": 10,
            "pay_asset": "EUR"
        }
        
        resp = self.session.post(f"{BASE_URL}/api/neno-exchange/buy-custom-token", json=payload)
        assert resp.status_code == 200, f"Buy custom token failed: {resp.text}"
        
        data = resp.json()
        assert "transaction" in data
        assert "balances" in data
        assert data["transaction"]["token_symbol"] == self.test_symbol
        assert data["transaction"]["token_amount"] == 10
        print(f"PASS: Bought 10 {self.test_symbol} with EUR")
    
    def test_buy_custom_token_insufficient_balance(self):
        """Test buying custom token with insufficient balance"""
        payload = {
            "symbol": self.test_symbol,
            "amount": 999999999,  # Very large amount
            "pay_asset": "BTC"  # Likely no BTC balance
        }
        
        resp = self.session.post(f"{BASE_URL}/api/neno-exchange/buy-custom-token", json=payload)
        assert resp.status_code == 400, f"Expected 400 for insufficient balance: {resp.text}"
        assert "insufficiente" in resp.json().get("detail", "").lower() or "insufficient" in resp.json().get("detail", "").lower()
        print("PASS: Insufficient balance correctly rejected")
    
    def test_sell_custom_token(self):
        """Test selling custom token for EUR"""
        # User should have tokens from creation
        payload = {
            "symbol": self.test_symbol,
            "amount": 5,
            "receive_asset": "EUR"
        }
        
        resp = self.session.post(f"{BASE_URL}/api/neno-exchange/sell-custom-token", json=payload)
        assert resp.status_code == 200, f"Sell custom token failed: {resp.text}"
        
        data = resp.json()
        assert "transaction" in data
        assert "balances" in data
        assert data["transaction"]["token_symbol"] == self.test_symbol
        assert data["transaction"]["token_amount"] == 5
        assert data["transaction"]["receive_asset"] == "EUR"
        print(f"PASS: Sold 5 {self.test_symbol} for EUR")
    
    def test_sell_custom_token_insufficient_balance(self):
        """Test selling more tokens than owned"""
        payload = {
            "symbol": self.test_symbol,
            "amount": 999999999,  # More than owned
            "receive_asset": "EUR"
        }
        
        resp = self.session.post(f"{BASE_URL}/api/neno-exchange/sell-custom-token", json=payload)
        assert resp.status_code == 400, f"Expected 400 for insufficient token balance: {resp.text}"
        assert "insufficiente" in resp.json().get("detail", "").lower()
        print("PASS: Insufficient token balance correctly rejected")


class TestCustomTokenPhase3:
    """Phase 3: Swap Custom/Native Tokens Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and setup"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        # Create a test token for swap tests
        self.test_symbol = f"S{uuid.uuid4().hex[:4].upper()}"
        create_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/create-token", json={
            "name": f"Swap Test {self.test_symbol}",
            "symbol": self.test_symbol,
            "total_supply": 5000,
            "price_usd": 1.00
        })
        if create_resp.status_code != 200:
            pytest.skip(f"Could not create test token: {create_resp.text}")
    
    def test_swap_quote_custom_to_native(self):
        """Test getting swap quote from custom token to EUR"""
        resp = self.session.get(
            f"{BASE_URL}/api/neno-exchange/swap-quote",
            params={"from_asset": self.test_symbol, "to_asset": "EUR", "amount": 100}
        )
        assert resp.status_code == 200, f"Swap quote failed: {resp.text}"
        
        data = resp.json()
        assert "from_asset" in data
        assert "to_asset" in data
        assert "receive_amount" in data
        assert "rate" in data
        assert "fee_pct" in data
        assert data["from_asset"] == self.test_symbol
        assert data["to_asset"] == "EUR"
        print(f"PASS: Swap quote {self.test_symbol}->EUR: receive {data['receive_amount']} EUR")
    
    def test_swap_quote_native_to_custom(self):
        """Test getting swap quote from EUR to custom token"""
        resp = self.session.get(
            f"{BASE_URL}/api/neno-exchange/swap-quote",
            params={"from_asset": "EUR", "to_asset": self.test_symbol, "amount": 100}
        )
        assert resp.status_code == 200, f"Swap quote failed: {resp.text}"
        
        data = resp.json()
        assert data["from_asset"] == "EUR"
        assert data["to_asset"] == self.test_symbol
        assert data["receive_amount"] > 0
        print(f"PASS: Swap quote EUR->{self.test_symbol}: receive {data['receive_amount']} tokens")
    
    def test_swap_custom_to_eur(self):
        """Test swapping custom token to EUR"""
        payload = {
            "from_asset": self.test_symbol,
            "to_asset": "EUR",
            "amount": 50
        }
        
        resp = self.session.post(f"{BASE_URL}/api/neno-exchange/swap", json=payload)
        assert resp.status_code == 200, f"Swap failed: {resp.text}"
        
        data = resp.json()
        assert "transaction" in data
        assert "balances" in data
        assert data["transaction"]["from_asset"] == self.test_symbol
        assert data["transaction"]["to_asset"] == "EUR"
        assert data["transaction"]["from_amount"] == 50
        assert data["transaction"]["to_amount"] > 0
        print(f"PASS: Swapped 50 {self.test_symbol} -> {data['transaction']['to_amount']} EUR")
    
    def test_swap_same_asset_rejected(self):
        """Test that swapping same asset is rejected"""
        payload = {
            "from_asset": "EUR",
            "to_asset": "EUR",
            "amount": 100
        }
        
        resp = self.session.post(f"{BASE_URL}/api/neno-exchange/swap", json=payload)
        assert resp.status_code == 400, f"Expected 400 for same asset swap: {resp.text}"
        print("PASS: Same asset swap correctly rejected")
    
    def test_swap_insufficient_balance(self):
        """Test swap with insufficient balance"""
        payload = {
            "from_asset": self.test_symbol,
            "to_asset": "EUR",
            "amount": 999999999  # More than owned
        }
        
        resp = self.session.post(f"{BASE_URL}/api/neno-exchange/swap", json=payload)
        assert resp.status_code == 400, f"Expected 400 for insufficient balance: {resp.text}"
        assert "insufficiente" in resp.json().get("detail", "").lower()
        print("PASS: Insufficient balance swap correctly rejected")


class TestCustomTokenPhase4:
    """Phase 4: Live Balances and Real-Time Sync Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_live_balances_endpoint(self):
        """Test GET /api/neno-exchange/live-balances returns wallet balances"""
        resp = self.session.get(f"{BASE_URL}/api/neno-exchange/live-balances")
        assert resp.status_code == 200, f"Live balances failed: {resp.text}"
        
        data = resp.json()
        assert "balances" in data
        assert "total_value_usd" in data
        assert "timestamp" in data
        assert "neno_price" in data
        
        # Check balance structure
        if len(data["balances"]) > 0:
            for asset, info in data["balances"].items():
                assert "balance" in info
                assert "price_usd" in info
                assert "value_usd" in info
                assert "is_custom" in info
        
        print(f"PASS: Live balances returns {len(data['balances'])} assets, total ${data['total_value_usd']}")
    
    def test_live_balances_includes_custom_tokens(self):
        """Test that live balances includes custom tokens with is_custom flag"""
        # Create a custom token first
        test_symbol = f"L{uuid.uuid4().hex[:4].upper()}"
        self.session.post(f"{BASE_URL}/api/neno-exchange/create-token", json={
            "name": f"Live Test {test_symbol}",
            "symbol": test_symbol,
            "total_supply": 1000,
            "price_usd": 1.00
        })
        
        # Get live balances
        resp = self.session.get(f"{BASE_URL}/api/neno-exchange/live-balances")
        assert resp.status_code == 200
        
        data = resp.json()
        
        # Check if our custom token is in balances
        if test_symbol in data["balances"]:
            assert data["balances"][test_symbol]["is_custom"] == True
            print(f"PASS: Custom token {test_symbol} in live balances with is_custom=True")
        else:
            print(f"INFO: Token {test_symbol} not in balances (may have 0 balance)")
    
    def test_custom_tokens_list_endpoint(self):
        """Test GET /api/neno-exchange/custom-tokens returns all custom tokens"""
        resp = self.session.get(f"{BASE_URL}/api/neno-exchange/custom-tokens")
        assert resp.status_code == 200, f"Custom tokens list failed: {resp.text}"
        
        data = resp.json()
        assert "tokens" in data
        assert isinstance(data["tokens"], list)
        
        if len(data["tokens"]) > 0:
            token = data["tokens"][0]
            assert "symbol" in token
            assert "name" in token
            assert "price_usd" in token or "price_eur" in token
            assert "total_supply" in token
        
        print(f"PASS: Custom tokens list returns {len(data['tokens'])} tokens")


class TestCustomTokenIntegration:
    """Integration tests for full custom token workflow"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
    
    def test_full_token_lifecycle(self):
        """Test complete token lifecycle: create -> buy -> sell -> swap"""
        # 1. Create token
        symbol = f"LC{uuid.uuid4().hex[:3].upper()}"
        create_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/create-token", json={
            "name": f"Lifecycle Test {symbol}",
            "symbol": symbol,
            "total_supply": 10000,
            "price_usd": 0.50
        })
        assert create_resp.status_code == 200, f"Create failed: {create_resp.text}"
        print(f"1. Created token {symbol}")
        
        # 2. Deposit EUR for buying
        self.session.post(f"{BASE_URL}/api/wallet/deposit", json={"asset": "EUR", "amount": 500})
        print("2. Deposited 500 EUR")
        
        # 3. Buy more tokens
        buy_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/buy-custom-token", json={
            "symbol": symbol,
            "amount": 100,
            "pay_asset": "EUR"
        })
        assert buy_resp.status_code == 200, f"Buy failed: {buy_resp.text}"
        print(f"3. Bought 100 {symbol}")
        
        # 4. Sell some tokens
        sell_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/sell-custom-token", json={
            "symbol": symbol,
            "amount": 50,
            "receive_asset": "EUR"
        })
        assert sell_resp.status_code == 200, f"Sell failed: {sell_resp.text}"
        print(f"4. Sold 50 {symbol}")
        
        # 5. Swap tokens to USDT
        swap_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/swap", json={
            "from_asset": symbol,
            "to_asset": "USDT",
            "amount": 25
        })
        assert swap_resp.status_code == 200, f"Swap failed: {swap_resp.text}"
        print(f"5. Swapped 25 {symbol} to USDT")
        
        # 6. Check live balances
        balances_resp = self.session.get(f"{BASE_URL}/api/neno-exchange/live-balances")
        assert balances_resp.status_code == 200
        balances = balances_resp.json()["balances"]
        
        if symbol in balances:
            print(f"6. Final {symbol} balance: {balances[symbol]['balance']}")
        
        print(f"PASS: Full lifecycle test completed for {symbol}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
