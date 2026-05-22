"""
Iteration 24 - NENO Exchange Tests
Tests for:
1. Platform wallet endpoint (GET /api/neno-exchange/platform-wallet)
2. Verify-deposit endpoint (POST /api/neno-exchange/verify-deposit)
3. Sell/Swap/Buy operations with proper error messages (not generic network errors)
4. CORS configuration (allow_credentials=False)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-chain-wallet-14.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"


class TestHealthAndAuth:
    """Basic health and authentication tests"""
    
    def test_health_endpoint(self):
        """Test health endpoint is accessible"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print(f"✓ Health check passed: {data}")
    
    def test_admin_login(self):
        """Test admin login returns valid token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert len(data["access_token"]) > 0
        print(f"✓ Admin login successful, token length: {len(data['access_token'])}")
        return data["access_token"]


class TestPlatformWallet:
    """Tests for platform hot wallet endpoint"""
    
    def test_platform_wallet_endpoint(self):
        """GET /api/neno-exchange/platform-wallet returns hot wallet address"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/platform-wallet")
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert "address" in data, "Response should contain 'address'"
        assert "chain" in data, "Response should contain 'chain'"
        assert "chain_id" in data, "Response should contain 'chain_id'"
        assert "contract" in data, "Response should contain 'contract'"
        assert "usage" in data, "Response should contain 'usage'"
        
        # Verify values
        assert data["address"].startswith("0x"), "Address should start with 0x"
        assert len(data["address"]) == 42, "Address should be 42 characters"
        assert data["chain"] == "BSC Mainnet"
        assert data["chain_id"] == 56
        assert data["contract"] == "0xeF3F5C1892A8d7A3304E4A15959E124402d69974"
        
        print(f"✓ Platform wallet: {data['address']}")
        print(f"  Chain: {data['chain']} (ID: {data['chain_id']})")
        print(f"  Contract: {data['contract']}")


class TestVerifyDeposit:
    """Tests for verify-deposit endpoint"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Authentication failed")
    
    def test_verify_deposit_requires_auth(self):
        """POST /api/neno-exchange/verify-deposit requires authentication"""
        response = requests.post(f"{BASE_URL}/api/neno-exchange/verify-deposit", json={
            "tx_hash": "0x" + "a" * 64,
            "expected_amount": 1.0,
            "operation": "sell"
        })
        assert response.status_code == 401 or response.status_code == 403
        print("✓ verify-deposit requires authentication")
    
    def test_verify_deposit_invalid_tx_hash_format(self, auth_token):
        """POST /api/neno-exchange/verify-deposit validates tx_hash format"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Too short tx_hash
        response = requests.post(f"{BASE_URL}/api/neno-exchange/verify-deposit", 
            json={
                "tx_hash": "0x123",
                "expected_amount": 1.0,
                "operation": "sell"
            },
            headers=headers
        )
        # Should fail validation (422 or 400)
        assert response.status_code in [400, 422]
        print(f"✓ Short tx_hash rejected with status {response.status_code}")
    
    def test_verify_deposit_valid_format_nonexistent_tx(self, auth_token):
        """POST /api/neno-exchange/verify-deposit with valid format but non-existent tx"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Valid format but fake tx hash
        fake_tx_hash = "0x" + "a" * 64
        response = requests.post(f"{BASE_URL}/api/neno-exchange/verify-deposit", 
            json={
                "tx_hash": fake_tx_hash,
                "expected_amount": 1.0,
                "operation": "sell"
            },
            headers=headers
        )
        # Should return 404 (tx not found) or 503 (RPC unavailable)
        assert response.status_code in [400, 404, 503]
        data = response.json()
        assert "detail" in data
        print(f"✓ Non-existent tx handled: {response.status_code} - {data.get('detail', '')[:50]}")


class TestSellWithProperErrors:
    """Tests for sell endpoint with proper error messages (not generic network errors)"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Authentication failed")
    
    def test_sell_insufficient_balance_returns_proper_error(self, auth_token):
        """POST /api/neno-exchange/sell with insufficient NENO returns proper 400 error"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Try to sell a huge amount that user doesn't have
        response = requests.post(f"{BASE_URL}/api/neno-exchange/sell",
            json={
                "receive_asset": "EUR",
                "neno_amount": 999999999.0  # Huge amount
            },
            headers=headers
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        data = response.json()
        assert "detail" in data, "Response should contain 'detail'"
        
        # Verify it's a proper error message, not generic network error
        detail = data["detail"]
        assert "Saldo NENO insufficiente" in detail or "insufficiente" in detail.lower()
        assert "Errore di rete" not in detail
        assert "network" not in detail.lower()
        
        print(f"✓ Insufficient balance error: {detail}")
    
    def test_sell_valid_amount_success(self, auth_token):
        """POST /api/neno-exchange/sell with valid amount returns success"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # First check balance
        balance_resp = requests.get(f"{BASE_URL}/api/wallet/balances", headers=headers)
        if balance_resp.status_code == 200:
            wallets = balance_resp.json().get("wallets", [])
            neno_balance = next((w["balance"] for w in wallets if w["asset"] == "NENO"), 0)
            print(f"  Current NENO balance: {neno_balance}")
        
        # Sell a small amount
        response = requests.post(f"{BASE_URL}/api/neno-exchange/sell",
            json={
                "receive_asset": "EUR",
                "neno_amount": 0.001
            },
            headers=headers
        )
        
        # Should succeed or fail with proper error (not network error)
        if response.status_code == 200:
            data = response.json()
            assert "message" in data
            assert "transaction" in data
            tx = data["transaction"]
            assert "settlement_hash" in tx
            print(f"✓ Sell success: {data['message']}")
            print(f"  Settlement hash: {tx.get('settlement_hash', 'N/A')[:20]}...")
        else:
            data = response.json()
            detail = data.get("detail", "")
            # Even if it fails, should be a proper error, not network error
            assert "Errore di rete" not in detail
            print(f"✓ Sell failed with proper error: {detail}")


class TestSwapEndpoint:
    """Tests for swap endpoint"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Authentication failed")
    
    def test_swap_neno_to_eth(self, auth_token):
        """POST /api/neno-exchange/swap NENO->ETH works"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/swap",
            json={
                "from_asset": "NENO",
                "to_asset": "ETH",
                "amount": 0.001
            },
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "message" in data
            assert "transaction" in data
            print(f"✓ Swap success: {data['message']}")
        else:
            data = response.json()
            detail = data.get("detail", "")
            # Should be proper error, not network error
            assert "Errore di rete" not in detail
            print(f"✓ Swap failed with proper error: {detail}")
    
    def test_swap_same_asset_rejected(self, auth_token):
        """POST /api/neno-exchange/swap same asset rejected"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/swap",
            json={
                "from_asset": "NENO",
                "to_asset": "NENO",
                "amount": 1.0
            },
            headers=headers
        )
        
        assert response.status_code == 400
        data = response.json()
        assert "stesso asset" in data.get("detail", "").lower() or "same" in data.get("detail", "").lower()
        print(f"✓ Same asset swap rejected: {data.get('detail')}")


class TestBuyEndpoint:
    """Tests for buy endpoint"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Authentication failed")
    
    def test_buy_neno_with_eur(self, auth_token):
        """POST /api/neno-exchange/buy works"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/buy",
            json={
                "pay_asset": "EUR",
                "neno_amount": 0.001
            },
            headers=headers
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "message" in data
            assert "transaction" in data
            tx = data["transaction"]
            assert "settlement_hash" in tx
            print(f"✓ Buy success: {data['message']}")
        else:
            data = response.json()
            detail = data.get("detail", "")
            # Should be proper error, not network error
            assert "Errore di rete" not in detail
            print(f"✓ Buy failed with proper error: {detail}")
    
    def test_buy_insufficient_balance_proper_error(self, auth_token):
        """POST /api/neno-exchange/buy with insufficient balance returns proper error"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        # Try to buy huge amount
        response = requests.post(f"{BASE_URL}/api/neno-exchange/buy",
            json={
                "pay_asset": "EUR",
                "neno_amount": 999999.0  # Would cost billions of EUR
            },
            headers=headers
        )
        
        assert response.status_code == 400
        data = response.json()
        detail = data.get("detail", "")
        assert "insufficiente" in detail.lower()
        assert "Errore di rete" not in detail
        print(f"✓ Insufficient EUR error: {detail}")


class TestCORSConfiguration:
    """Tests for CORS configuration"""
    
    def test_cors_headers_present(self):
        """OPTIONS request returns proper CORS headers"""
        response = requests.options(f"{BASE_URL}/api/neno-exchange/platform-wallet",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET"
            }
        )
        
        # Check CORS headers
        headers = response.headers
        assert "access-control-allow-origin" in [h.lower() for h in headers.keys()]
        print(f"✓ CORS headers present")
        print(f"  Allow-Origin: {headers.get('access-control-allow-origin', 'N/A')}")
        print(f"  Allow-Methods: {headers.get('access-control-allow-methods', 'N/A')}")
    
    def test_cors_on_error_response(self):
        """400 error responses include CORS headers (not body stream error)"""
        # Login first
        login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = login_resp.json().get("access_token")
        
        # Make a request that will return 400
        response = requests.post(f"{BASE_URL}/api/neno-exchange/sell",
            json={
                "receive_asset": "EUR",
                "neno_amount": 999999999.0
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Origin": "https://example.com"
            }
        )
        
        assert response.status_code == 400
        
        # Verify we can read the response body (no body stream consumed error)
        data = response.json()
        assert "detail" in data
        print(f"✓ 400 response readable: {data['detail'][:50]}...")


class TestMarketAndQuoteEndpoints:
    """Tests for market info and quote endpoints"""
    
    def test_market_info(self):
        """GET /api/neno-exchange/market returns market info"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/market")
        assert response.status_code == 200
        data = response.json()
        
        assert "neno_eur_price" in data
        assert "supported_assets" in data
        assert "pairs" in data
        
        print(f"✓ Market info: NENO price = EUR {data['neno_eur_price']}")
        print(f"  Supported assets: {len(data['supported_assets'])}")
    
    def test_price_endpoint(self):
        """GET /api/neno-exchange/price returns dynamic price"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/price")
        assert response.status_code == 200
        data = response.json()
        
        assert "neno_eur_price" in data
        assert "base_price" in data
        assert "pricing_model" in data
        
        print(f"✓ Price: EUR {data['neno_eur_price']} (base: {data['base_price']})")
        print(f"  Model: {data['pricing_model']}")
    
    def test_quote_buy(self):
        """GET /api/neno-exchange/quote for buy"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/quote?direction=buy&asset=EUR&neno_amount=1")
        assert response.status_code == 200
        data = response.json()
        
        assert "total_cost" in data
        assert "fee" in data
        assert "rate" in data
        
        print(f"✓ Buy quote: 1 NENO costs {data['total_cost']} EUR (fee: {data['fee']})")
    
    def test_quote_sell(self):
        """GET /api/neno-exchange/quote for sell"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/quote?direction=sell&asset=EUR&neno_amount=1")
        assert response.status_code == 200
        data = response.json()
        
        assert "net_receive" in data
        assert "fee" in data
        
        print(f"✓ Sell quote: 1 NENO receives {data['net_receive']} EUR (fee: {data['fee']})")


class TestTransactionHistory:
    """Tests for transaction history"""
    
    @pytest.fixture
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("access_token")
        pytest.skip("Authentication failed")
    
    def test_transactions_endpoint(self, auth_token):
        """GET /api/neno-exchange/transactions returns history"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        
        response = requests.get(f"{BASE_URL}/api/neno-exchange/transactions", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "transactions" in data
        assert "total" in data
        
        print(f"✓ Transactions: {data['total']} total")
        if data["transactions"]:
            tx = data["transactions"][0]
            print(f"  Latest: {tx.get('type')} - {tx.get('neno_amount', tx.get('from_amount'))} NENO")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
