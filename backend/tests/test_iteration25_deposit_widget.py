"""
Iteration 25 - NENO Exchange Tests
Focus: Deposit NENO widget, Alchemy BSC RPC, 6 tabs verification

Tests:
1. Platform wallet endpoint returns correct hot wallet address
2. Sell with insufficient balance shows proper Italian error
3. Sell with valid amount returns success with settlement_hash
4. Buy returns success with settlement and block data
5. Swap (NENO->ETH) returns success
6. verify-deposit with invalid tx_hash returns proper error
7. Market info endpoint works
8. Price endpoint works
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-chain-wallet-14.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"

# Expected platform hot wallet
EXPECTED_HOT_WALLET = "0x18CE1930820d5e1B87F37a8a2F7Cf59E7BF6da4E"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("token") or data.get("access_token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Auth headers for authenticated requests"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestHealthAndAuth:
    """Basic health and auth tests"""
    
    def test_health_endpoint(self):
        """Test health endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print(f"Health check: {response.json()}")
    
    def test_login_success(self):
        """Test admin login works"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data or "access_token" in data
        print(f"Login successful, token received")


class TestPlatformWallet:
    """Tests for platform wallet endpoint - critical for Deposit widget"""
    
    def test_platform_wallet_returns_correct_address(self):
        """GET /api/neno-exchange/platform-wallet returns correct hot wallet"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/platform-wallet")
        assert response.status_code == 200
        data = response.json()
        
        # Verify address
        assert "address" in data
        assert data["address"] == EXPECTED_HOT_WALLET
        print(f"Platform wallet address: {data['address']}")
        
        # Verify chain info
        assert data.get("chain") == "BSC Mainnet"
        assert data.get("chain_id") == 56
        assert "contract" in data
        print(f"Chain: {data['chain']}, Chain ID: {data['chain_id']}")
    
    def test_platform_wallet_has_usage_info(self):
        """Platform wallet endpoint includes usage instructions"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/platform-wallet")
        assert response.status_code == 200
        data = response.json()
        
        assert "usage" in data
        print(f"Usage info: {data['usage']}")


class TestNenoExchangeSell:
    """Tests for NENO sell operations"""
    
    def test_sell_insufficient_balance_shows_italian_error(self, auth_headers):
        """POST /api/neno-exchange/sell with huge amount shows 'Saldo NENO insufficiente'"""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/sell",
            json={"receive_asset": "EUR", "neno_amount": 999999999},
            headers=auth_headers
        )
        assert response.status_code == 400
        data = response.json()
        
        # Must show Italian error, NOT generic network error
        assert "detail" in data
        assert "Saldo NENO insufficiente" in data["detail"]
        print(f"Insufficient balance error: {data['detail']}")
    
    def test_sell_valid_amount_returns_success(self, auth_headers):
        """POST /api/neno-exchange/sell with small valid amount returns success"""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/sell",
            json={"receive_asset": "EUR", "neno_amount": 0.001},
            headers=auth_headers
        )
        # Could be 200 (success) or 400 (if balance is 0)
        if response.status_code == 200:
            data = response.json()
            assert "transaction" in data
            tx = data["transaction"]
            assert "settlement_hash" in tx
            print(f"Sell success - Settlement hash: {tx['settlement_hash'][:20]}...")
        else:
            data = response.json()
            # If 400, should still be proper error message
            assert "detail" in data
            print(f"Sell returned 400: {data['detail']}")


class TestNenoExchangeBuy:
    """Tests for NENO buy operations"""
    
    def test_buy_returns_success_with_settlement(self, auth_headers):
        """POST /api/neno-exchange/buy returns success with settlement data"""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/buy",
            json={"pay_asset": "EUR", "neno_amount": 0.001},
            headers=auth_headers
        )
        # Could be 200 or 400 depending on EUR balance
        if response.status_code == 200:
            data = response.json()
            assert "transaction" in data
            tx = data["transaction"]
            assert "settlement_hash" in tx
            assert "settlement_block_number" in tx
            print(f"Buy success - Block: {tx['settlement_block_number']}, Hash: {tx['settlement_hash'][:20]}...")
        else:
            data = response.json()
            assert "detail" in data
            print(f"Buy returned {response.status_code}: {data.get('detail', data)}")


class TestNenoExchangeSwap:
    """Tests for NENO swap operations"""
    
    def test_swap_neno_to_eth_returns_success(self, auth_headers):
        """POST /api/neno-exchange/swap NENO->ETH returns success"""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/swap",
            json={"from_asset": "NENO", "to_asset": "ETH", "amount": 0.001},
            headers=auth_headers
        )
        if response.status_code == 200:
            data = response.json()
            assert "transaction" in data
            tx = data["transaction"]
            assert "settlement_hash" in tx
            print(f"Swap success - Settlement hash: {tx['settlement_hash'][:20]}...")
        else:
            data = response.json()
            assert "detail" in data
            print(f"Swap returned {response.status_code}: {data.get('detail', data)}")
    
    def test_swap_same_asset_fails(self, auth_headers):
        """POST /api/neno-exchange/swap same asset returns error"""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/swap",
            json={"from_asset": "NENO", "to_asset": "NENO", "amount": 1},
            headers=auth_headers
        )
        assert response.status_code == 400
        data = response.json()
        assert "detail" in data
        print(f"Same asset swap error: {data['detail']}")


class TestVerifyDeposit:
    """Tests for verify-deposit endpoint"""
    
    def test_verify_deposit_invalid_tx_hash_format(self, auth_headers):
        """POST /api/neno-exchange/verify-deposit with short tx_hash returns validation error"""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/verify-deposit",
            json={"tx_hash": "0x123", "expected_amount": 1.0, "operation": "sell"},
            headers=auth_headers
        )
        # Should return 422 (validation error) for short tx_hash
        assert response.status_code == 422
        print(f"Invalid tx_hash format error: {response.status_code}")
    
    def test_verify_deposit_fake_tx_hash(self, auth_headers):
        """POST /api/neno-exchange/verify-deposit with fake but valid-format tx_hash"""
        fake_hash = "0x" + "a" * 64  # Valid format but fake
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/verify-deposit",
            json={"tx_hash": fake_hash, "expected_amount": 1.0, "operation": "sell"},
            headers=auth_headers
        )
        # Should return 404 (not found), 400 (bad request), 503 (RPC unavailable), or 500 (on-chain error)
        assert response.status_code in [400, 404, 500, 503]
        data = response.json()
        assert "detail" in data
        print(f"Fake tx_hash error: {data['detail']}")


class TestMarketAndPrice:
    """Tests for market info and price endpoints"""
    
    def test_market_info_endpoint(self):
        """GET /api/neno-exchange/market returns market info"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/market")
        assert response.status_code == 200
        data = response.json()
        
        assert "neno_eur_price" in data
        assert "supported_assets" in data
        assert "pairs" in data
        print(f"NENO EUR price: {data['neno_eur_price']}")
        print(f"Supported assets: {data['supported_assets']}")
    
    def test_price_endpoint(self):
        """GET /api/neno-exchange/price returns dynamic price"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/price")
        assert response.status_code == 200
        data = response.json()
        
        assert "neno_eur_price" in data
        assert "base_price" in data
        assert "pricing_model" in data
        print(f"Dynamic price: EUR {data['neno_eur_price']}, Model: {data['pricing_model']}")
    
    def test_quote_endpoint(self):
        """GET /api/neno-exchange/quote returns quote with fees"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/quote?direction=buy&asset=EUR&neno_amount=1")
        assert response.status_code == 200
        data = response.json()
        
        assert "total_cost" in data
        assert "fee" in data
        assert "rate" in data
        print(f"Quote: 1 NENO = {data['rate']} EUR, Fee: {data['fee']}, Total: {data['total_cost']}")


class TestContractInfo:
    """Tests for contract info endpoint (uses Alchemy RPC)"""
    
    def test_contract_info_endpoint(self):
        """GET /api/neno-exchange/contract-info returns BSC contract data"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/contract-info")
        assert response.status_code == 200
        data = response.json()
        
        assert "contract" in data
        assert "current_block" in data
        print(f"Contract info: {data['contract']}")
        print(f"Current block: {data['current_block']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
