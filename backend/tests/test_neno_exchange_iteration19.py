"""
NENO Exchange Backend Tests - Iteration 19
Tests all NENO Exchange functionality:
- Market info, price, quotes
- Buy/Sell NENO
- Swap any token pair
- Off-ramp to card/bank
- Create custom tokens
- Transaction history
- Wallet balance updates
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-chain-wallet-14.preview.emergentagent.com')

class TestNenoExchangePublicEndpoints:
    """Test public NENO Exchange endpoints (no auth required)"""
    
    def test_market_info(self):
        """GET /api/neno-exchange/market returns correct data"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/market")
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "neno_eur_price" in data
        assert "neno_usd_price" in data
        assert "fee_percent" in data
        assert "supported_assets" in data
        assert "pairs" in data
        assert "custom_tokens" in data
        
        # Verify values
        assert data["neno_eur_price"] >= 9500  # Base is 10000 with 5% max deviation
        assert data["neno_eur_price"] <= 10500
        assert data["fee_percent"] == 0.3
        assert "EUR" in data["supported_assets"]
        assert "ETH" in data["supported_assets"]
        assert "BTC" in data["supported_assets"]
        print(f"Market info: NENO price = EUR {data['neno_eur_price']}, {len(data['supported_assets'])} assets")
    
    def test_dynamic_price(self):
        """GET /api/neno-exchange/price returns dynamic pricing"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/price")
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "neno_eur_price" in data
        assert "base_price" in data
        assert "price_shift" in data
        assert "shift_pct" in data
        assert "buy_volume_24h" in data
        assert "sell_volume_24h" in data
        assert "net_pressure" in data
        assert "pricing_model" in data
        assert "max_deviation" in data
        
        # Verify values
        assert data["base_price"] == 10000
        assert data["pricing_model"] == "dynamic_orderbook"
        assert data["max_deviation"] == "5.0%"
        print(f"Dynamic price: EUR {data['neno_eur_price']}, shift: {data['shift_pct']}%")
    
    def test_buy_quote(self):
        """GET /api/neno-exchange/quote?direction=buy returns quote"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/quote?direction=buy&asset=EUR&neno_amount=1")
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert data["direction"] == "buy"
        assert data["neno_amount"] == 1
        assert data["pay_asset"] == "EUR"
        assert "rate" in data
        assert "neno_eur_price" in data
        assert "gross_cost" in data
        assert "fee" in data
        assert "fee_percent" in data
        assert "total_cost" in data
        assert "summary" in data
        
        # Verify calculations
        assert data["fee_percent"] == 0.3
        assert data["total_cost"] == data["gross_cost"] + data["fee"]
        print(f"Buy quote: 1 NENO costs {data['total_cost']} EUR (fee: {data['fee']})")
    
    def test_sell_quote(self):
        """GET /api/neno-exchange/quote?direction=sell returns quote"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/quote?direction=sell&asset=EUR&neno_amount=1")
        assert response.status_code == 200
        data = response.json()
        
        assert data["direction"] == "sell"
        assert data["neno_amount"] == 1
        assert data["receive_asset"] == "EUR"
        assert "net_receive" in data
        assert data["net_receive"] == data["gross_value"] - data["fee"]
        print(f"Sell quote: 1 NENO receives {data['net_receive']} EUR")
    
    def test_swap_quote_neno_to_eth(self):
        """GET /api/neno-exchange/swap-quote?from_asset=NENO&to_asset=ETH returns quote"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/swap-quote?from_asset=NENO&to_asset=ETH&amount=1")
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert data["from_asset"] == "NENO"
        assert data["to_asset"] == "ETH"
        assert data["amount"] == 1
        assert "receive_amount" in data
        assert "rate" in data
        assert "eur_value" in data
        assert "fee_eur" in data
        assert "fee_pct" in data
        
        # Verify values
        assert data["fee_pct"] == 0.3
        assert data["receive_amount"] > 0
        print(f"Swap quote: 1 NENO -> {data['receive_amount']} ETH (rate: {data['rate']})")
    
    def test_swap_quote_eth_to_btc(self):
        """GET /api/neno-exchange/swap-quote for non-NENO pair"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/swap-quote?from_asset=ETH&to_asset=BTC&amount=1")
        assert response.status_code == 200
        data = response.json()
        
        assert data["from_asset"] == "ETH"
        assert data["to_asset"] == "BTC"
        assert data["receive_amount"] > 0
        print(f"Swap quote: 1 ETH -> {data['receive_amount']} BTC")


class TestNenoExchangeAuthenticatedEndpoints:
    """Test authenticated NENO Exchange endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@neonobleramp.com",
            "password": "Admin1234!"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        self.token = response.json()["token"]
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.token}"
        }
    
    def test_get_transactions(self):
        """GET /api/neno-exchange/transactions returns transaction list"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/transactions", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "transactions" in data
        assert "total" in data
        assert isinstance(data["transactions"], list)
        print(f"Transactions: {data['total']} total")
    
    def test_get_wallet_balances(self):
        """GET /api/wallet/balances returns wallet balances"""
        response = requests.get(f"{BASE_URL}/api/wallet/balances", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "wallets" in data
        assert isinstance(data["wallets"], list)
        
        # Find NENO balance
        neno_wallet = next((w for w in data["wallets"] if w["asset"] == "NENO"), None)
        if neno_wallet:
            print(f"NENO balance: {neno_wallet['balance']}")
        else:
            print("No NENO balance found")
    
    def test_buy_neno_small_amount(self):
        """POST /api/neno-exchange/buy with small amount succeeds"""
        # First check EUR balance
        balances_resp = requests.get(f"{BASE_URL}/api/wallet/balances", headers=self.headers)
        balances = balances_resp.json()
        eur_wallet = next((w for w in balances["wallets"] if w["asset"] == "EUR"), None)
        
        if not eur_wallet or eur_wallet["balance"] < 15:
            pytest.skip("Insufficient EUR balance for buy test")
        
        initial_neno = next((w["balance"] for w in balances["wallets"] if w["asset"] == "NENO"), 0)
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/buy", headers=self.headers, json={
            "pay_asset": "EUR",
            "neno_amount": 0.001
        })
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert "transaction" in data
        assert "balances" in data
        assert data["transaction"]["type"] == "buy_neno"
        assert data["balances"]["NENO"] > initial_neno
        print(f"Buy success: {data['message']}")
    
    def test_sell_neno_small_amount(self):
        """POST /api/neno-exchange/sell with small amount succeeds"""
        # First check NENO balance
        balances_resp = requests.get(f"{BASE_URL}/api/wallet/balances", headers=self.headers)
        balances = balances_resp.json()
        neno_wallet = next((w for w in balances["wallets"] if w["asset"] == "NENO"), None)
        
        if not neno_wallet or neno_wallet["balance"] < 0.001:
            pytest.skip("Insufficient NENO balance for sell test")
        
        initial_eur = next((w["balance"] for w in balances["wallets"] if w["asset"] == "EUR"), 0)
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/sell", headers=self.headers, json={
            "receive_asset": "EUR",
            "neno_amount": 0.001
        })
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert "transaction" in data
        assert data["transaction"]["type"] == "sell_neno"
        print(f"Sell success: {data['message']}")
    
    def test_swap_neno_to_eth(self):
        """POST /api/neno-exchange/swap NENO to ETH succeeds"""
        # Check NENO balance
        balances_resp = requests.get(f"{BASE_URL}/api/wallet/balances", headers=self.headers)
        balances = balances_resp.json()
        neno_wallet = next((w for w in balances["wallets"] if w["asset"] == "NENO"), None)
        
        if not neno_wallet or neno_wallet["balance"] < 0.001:
            pytest.skip("Insufficient NENO balance for swap test")
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/swap", headers=self.headers, json={
            "from_asset": "NENO",
            "to_asset": "ETH",
            "amount": 0.001
        })
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert "transaction" in data
        assert data["transaction"]["type"] == "swap"
        assert data["transaction"]["from_asset"] == "NENO"
        assert data["transaction"]["to_asset"] == "ETH"
        print(f"Swap success: {data['message']}")
    
    def test_create_token_unique(self):
        """POST /api/neno-exchange/create-token creates new token"""
        # Generate unique symbol
        unique_symbol = f"TT{int(time.time()) % 10000}"
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/create-token", headers=self.headers, json={
            "symbol": unique_symbol,
            "name": f"Test Token {unique_symbol}",
            "price_eur": 1.0,
            "total_supply": 1000
        })
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert "token" in data
        assert data["token"]["symbol"] == unique_symbol
        assert data["token"]["price_eur"] == 1.0
        assert data["balance"] == 1000
        print(f"Token created: {unique_symbol} @ EUR 1.0, supply: 1000")
    
    def test_create_token_duplicate_fails(self):
        """POST /api/neno-exchange/create-token with existing symbol fails"""
        # TEST token already exists from previous testing
        response = requests.post(f"{BASE_URL}/api/neno-exchange/create-token", headers=self.headers, json={
            "symbol": "TEST",
            "name": "Test Token",
            "price_eur": 0.50,
            "total_supply": 1000
        })
        assert response.status_code == 400
        assert "esiste gia" in response.json()["detail"]
        print("Duplicate token correctly rejected")
    
    def test_offramp_bank(self):
        """POST /api/neno-exchange/offramp to bank succeeds"""
        # Check NENO balance
        balances_resp = requests.get(f"{BASE_URL}/api/wallet/balances", headers=self.headers)
        balances = balances_resp.json()
        neno_wallet = next((w for w in balances["wallets"] if w["asset"] == "NENO"), None)
        
        if not neno_wallet or neno_wallet["balance"] < 0.001:
            pytest.skip("Insufficient NENO balance for offramp test")
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/offramp", headers=self.headers, json={
            "neno_amount": 0.001,
            "destination": "bank",
            "destination_iban": "IT60X0542811101000000123456",
            "beneficiary_name": "Test User"
        })
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert "transaction" in data
        assert data["transaction"]["destination"] == "bank"
        print(f"Offramp success: {data['message']}")
    
    def test_offramp_card_requires_card_id(self):
        """POST /api/neno-exchange/offramp to card without card_id fails"""
        response = requests.post(f"{BASE_URL}/api/neno-exchange/offramp", headers=self.headers, json={
            "neno_amount": 0.001,
            "destination": "card"
        })
        assert response.status_code == 400
        assert "card_id" in response.json()["detail"]
        print("Card offramp without card_id correctly rejected")
    
    def test_swap_same_asset_fails(self):
        """POST /api/neno-exchange/swap same asset fails"""
        response = requests.post(f"{BASE_URL}/api/neno-exchange/swap", headers=self.headers, json={
            "from_asset": "NENO",
            "to_asset": "NENO",
            "amount": 1
        })
        assert response.status_code == 400
        assert "stesso asset" in response.json()["detail"]
        print("Same asset swap correctly rejected")
    
    def test_buy_insufficient_balance_fails(self):
        """POST /api/neno-exchange/buy with insufficient balance fails"""
        response = requests.post(f"{BASE_URL}/api/neno-exchange/buy", headers=self.headers, json={
            "pay_asset": "EUR",
            "neno_amount": 999999  # Very large amount
        })
        assert response.status_code == 400
        assert "insufficiente" in response.json()["detail"]
        print("Insufficient balance correctly rejected")


class TestNenoExchangeCustomTokens:
    """Test custom token functionality"""
    
    def test_list_custom_tokens(self):
        """GET /api/neno-exchange/custom-tokens returns token list"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/custom-tokens")
        assert response.status_code == 200
        data = response.json()
        
        assert "tokens" in data
        assert isinstance(data["tokens"], list)
        
        # TEST token should exist
        test_token = next((t for t in data["tokens"] if t["symbol"] == "TEST"), None)
        if test_token:
            assert test_token["price_eur"] == 0.5
            print(f"Found TEST token: EUR {test_token['price_eur']}")
        print(f"Total custom tokens: {len(data['tokens'])}")
    
    def test_swap_with_custom_token(self):
        """Swap quote works with custom token"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/swap-quote?from_asset=TEST&to_asset=EUR&amount=100")
        assert response.status_code == 200
        data = response.json()
        
        assert data["from_asset"] == "TEST"
        assert data["to_asset"] == "EUR"
        assert data["receive_amount"] > 0
        print(f"Custom token swap: 100 TEST -> {data['receive_amount']} EUR")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
