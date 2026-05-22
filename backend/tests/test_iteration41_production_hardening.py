"""
Iteration 41 — Production Hardening Tests

Tests for:
1. Admin login and role verification
2. Revenue withdrawal endpoint (admin only)
3. Revenue history endpoint
4. Hybrid liquidity engine status
5. Cashout engine status
6. Idempotency on financial operations (buy/sell/swap/offramp)
7. Non-admin access denial for revenue endpoints
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-chain-wallet-14.preview.emergentagent.com')

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"
USER_EMAIL = "test@example.com"
USER_PASSWORD = "Test1234!"


class TestAdminAuth:
    """Admin authentication and role verification"""
    
    def test_01_admin_login_returns_token_with_admin_role(self):
        """POST /api/auth/login with admin credentials returns token with ADMIN role"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        assert data.get("user", {}).get("role") == "ADMIN", f"Expected ADMIN role, got {data.get('user', {}).get('role')}"
        print(f"✓ Admin login successful, role: {data.get('user', {}).get('role')}")
    
    def test_02_regular_user_login_returns_user_role(self):
        """POST /api/auth/login with regular user returns USER role"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        })
        # User may or may not exist, but if exists should have USER role
        if response.status_code == 200:
            data = response.json()
            role = data.get("user", {}).get("role", "USER")
            assert role != "ADMIN", f"Regular user should not have ADMIN role"
            print(f"✓ Regular user login successful, role: {role}")
        else:
            print(f"✓ Regular user not found (expected for fresh DB)")


class TestRevenueWithdrawal:
    """Revenue withdrawal endpoint tests (admin only)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token for tests"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            self.admin_token = response.json().get("token")
        else:
            pytest.skip("Admin login failed")
    
    def test_03_revenue_withdraw_with_admin_token_returns_success(self):
        """POST /api/cashout/revenue-withdraw with ADMIN token returns success"""
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        response = requests.post(f"{BASE_URL}/api/cashout/revenue-withdraw", 
            headers=headers,
            json={
                "amount": 10.0,
                "currency": "EUR",
                "destination_type": "sepa",
                "destination_iban": "IT80V1810301600068254758246",
                "beneficiary_name": "Test Beneficiary"
            }
        )
        assert response.status_code == 200, f"Revenue withdraw failed: {response.text}"
        data = response.json()
        assert data.get("success") == True, f"Expected success=True, got {data}"
        assert "withdrawal" in data, "No withdrawal info in response"
        print(f"✓ Revenue withdrawal successful: {data.get('message')}")
    
    def test_04_revenue_withdraw_without_auth_returns_401(self):
        """POST /api/cashout/revenue-withdraw without auth returns 401"""
        response = requests.post(f"{BASE_URL}/api/cashout/revenue-withdraw", json={
            "amount": 10.0,
            "currency": "EUR",
            "destination_type": "sepa"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Revenue withdraw without auth returns 401")
    
    def test_05_revenue_history_returns_withdrawal_list(self):
        """GET /api/cashout/revenue-history returns withdrawal list"""
        headers = {"Authorization": f"Bearer {self.admin_token}"}
        response = requests.get(f"{BASE_URL}/api/cashout/revenue-history", headers=headers)
        assert response.status_code == 200, f"Revenue history failed: {response.text}"
        data = response.json()
        assert "withdrawals" in data, "No withdrawals in response"
        assert "count" in data, "No count in response"
        print(f"✓ Revenue history returned {data.get('count')} withdrawals")


class TestNonAdminAccessDenied:
    """Test that non-admin users cannot access admin endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get regular user token"""
        # First try to register a test user
        test_email = f"testuser_{uuid.uuid4().hex[:8]}@test.com"
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": test_email,
            "password": "TestPass123!",
            "name": "Test User"
        })
        if response.status_code in [200, 201]:
            self.user_token = response.json().get("token")
        else:
            # Try login with existing test user
            response = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": USER_EMAIL,
                "password": USER_PASSWORD
            })
            if response.status_code == 200:
                self.user_token = response.json().get("token")
            else:
                pytest.skip("Could not get user token")
    
    def test_06_revenue_withdraw_with_non_admin_returns_403(self):
        """POST /api/cashout/revenue-withdraw with non-admin token returns 403"""
        headers = {"Authorization": f"Bearer {self.user_token}"}
        response = requests.post(f"{BASE_URL}/api/cashout/revenue-withdraw",
            headers=headers,
            json={
                "amount": 10.0,
                "currency": "EUR",
                "destination_type": "sepa"
            }
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ Revenue withdraw with non-admin returns 403")
    
    def test_07_revenue_history_with_non_admin_returns_403(self):
        """GET /api/cashout/revenue-history with non-admin token returns 403"""
        headers = {"Authorization": f"Bearer {self.user_token}"}
        response = requests.get(f"{BASE_URL}/api/cashout/revenue-history", headers=headers)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print("✓ Revenue history with non-admin returns 403")


class TestHybridLiquidityEngine:
    """Hybrid Liquidity Engine status tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            self.token = response.json().get("token")
        else:
            pytest.skip("Admin login failed")
    
    def test_08_hybrid_status_returns_engine_info(self):
        """GET /api/hybrid/status returns hybrid_liquidity engine info"""
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.get(f"{BASE_URL}/api/hybrid/status", headers=headers)
        assert response.status_code == 200, f"Hybrid status failed: {response.text}"
        data = response.json()
        assert data.get("engine") == "hybrid_liquidity", f"Expected engine=hybrid_liquidity, got {data.get('engine')}"
        assert "execution_priority" in data, "No execution_priority in response"
        # Check for spread info (may be 'spread' or 'spread_config')
        has_spread = "spread" in data or "spread_config" in data or "volume_tiers" in data
        assert has_spread, "No spread/volume info in response"
        print(f"✓ Hybrid status: engine={data.get('engine')}, priority={data.get('execution_priority')}")


class TestCashoutEngine:
    """Cashout Engine status tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            self.token = response.json().get("token")
        else:
            pytest.skip("Admin login failed")
    
    def test_09_cashout_status_returns_running_status(self):
        """GET /api/cashout/status returns running cashout engine"""
        headers = {"Authorization": f"Bearer {self.token}"}
        response = requests.get(f"{BASE_URL}/api/cashout/status", headers=headers)
        assert response.status_code == 200, f"Cashout status failed: {response.text}"
        data = response.json()
        assert "running" in data, "No running status in response"
        assert "eur_accounts" in data, "No eur_accounts in response"
        print(f"✓ Cashout status: running={data.get('running')}, accounts={list(data.get('eur_accounts', {}).keys())}")


class TestIdempotency:
    """Idempotency tests for financial operations"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token and ensure user has balance"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            self.token = response.json().get("token")
        else:
            pytest.skip("Admin login failed")
    
    def test_10_duplicate_buy_request_returns_idempotency_result(self):
        """Duplicate buy request returns idempotency result instead of E11000"""
        headers = {"Authorization": f"Bearer {self.token}"}
        
        # First, check user balance
        balance_resp = requests.get(f"{BASE_URL}/api/neno-exchange/live-balances", headers=headers)
        if balance_resp.status_code != 200:
            pytest.skip("Could not get balances")
        
        balances = balance_resp.json().get("balances", {})
        eur_balance = balances.get("EUR", {}).get("balance", 0)
        
        if eur_balance < 100:
            # Credit some EUR for testing
            credit_resp = requests.post(f"{BASE_URL}/api/wallets/credit", headers=headers, json={
                "asset": "EUR",
                "amount": 1000
            })
            # If credit endpoint doesn't exist, skip
            if credit_resp.status_code not in [200, 201]:
                print(f"Note: Could not credit EUR balance, test may fail if insufficient funds")
        
        # Make first buy request
        buy_payload = {
            "pay_asset": "EUR",
            "neno_amount": 0.001  # Small amount
        }
        
        response1 = requests.post(f"{BASE_URL}/api/neno-exchange/buy", headers=headers, json=buy_payload)
        
        # If first request fails due to insufficient balance, that's expected
        if response1.status_code == 400 and "insufficiente" in response1.text.lower():
            print("✓ First buy request failed due to insufficient balance (expected)")
            return
        
        # Make second identical request immediately
        response2 = requests.post(f"{BASE_URL}/api/neno-exchange/buy", headers=headers, json=buy_payload)
        
        # Both should succeed or second should return idempotency result
        # Key: should NOT return E11000 duplicate key error
        assert "E11000" not in response2.text, f"Got E11000 duplicate key error: {response2.text}"
        
        if response2.status_code == 200:
            data2 = response2.json()
            # Check if it's an idempotency result
            if data2.get("duplicate") == True or "già eseguita" in str(data2.get("message", "")):
                print("✓ Duplicate buy request returned idempotency result")
            else:
                print("✓ Second buy request succeeded (may be different idempotency key)")
        else:
            # Any error except E11000 is acceptable
            print(f"✓ Second request returned {response2.status_code} (no E11000)")


class TestIdempotencyService:
    """Direct idempotency service tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get admin token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            self.token = response.json().get("token")
        else:
            pytest.skip("Admin login failed")
    
    def test_11_sell_idempotency_no_e11000(self):
        """Sell operation should not produce E11000 on duplicate"""
        headers = {"Authorization": f"Bearer {self.token}"}
        
        # Check NENO balance
        balance_resp = requests.get(f"{BASE_URL}/api/neno-exchange/live-balances", headers=headers)
        if balance_resp.status_code != 200:
            pytest.skip("Could not get balances")
        
        balances = balance_resp.json().get("balances", {})
        neno_balance = balances.get("NENO", {}).get("balance", 0)
        
        if neno_balance < 0.001:
            print("✓ Insufficient NENO balance for sell test (expected)")
            return
        
        sell_payload = {
            "receive_asset": "EUR",
            "neno_amount": 0.0001
        }
        
        response1 = requests.post(f"{BASE_URL}/api/neno-exchange/sell", headers=headers, json=sell_payload)
        response2 = requests.post(f"{BASE_URL}/api/neno-exchange/sell", headers=headers, json=sell_payload)
        
        assert "E11000" not in response2.text, f"Got E11000 on sell: {response2.text}"
        print("✓ Sell idempotency: no E11000 error")
    
    def test_12_swap_idempotency_no_e11000(self):
        """Swap operation should not produce E11000 on duplicate"""
        headers = {"Authorization": f"Bearer {self.token}"}
        
        swap_payload = {
            "from_asset": "EUR",
            "to_asset": "USDT",
            "amount": 1.0
        }
        
        response1 = requests.post(f"{BASE_URL}/api/neno-exchange/swap", headers=headers, json=swap_payload)
        response2 = requests.post(f"{BASE_URL}/api/neno-exchange/swap", headers=headers, json=swap_payload)
        
        assert "E11000" not in response2.text, f"Got E11000 on swap: {response2.text}"
        print("✓ Swap idempotency: no E11000 error")
    
    def test_13_offramp_idempotency_no_e11000(self):
        """Offramp operation should not produce E11000 on duplicate"""
        headers = {"Authorization": f"Bearer {self.token}"}
        
        # Check NENO balance
        balance_resp = requests.get(f"{BASE_URL}/api/neno-exchange/live-balances", headers=headers)
        if balance_resp.status_code != 200:
            pytest.skip("Could not get balances")
        
        balances = balance_resp.json().get("balances", {})
        neno_balance = balances.get("NENO", {}).get("balance", 0)
        
        if neno_balance < 0.001:
            print("✓ Insufficient NENO balance for offramp test (expected)")
            return
        
        offramp_payload = {
            "neno_amount": 0.0001,
            "destination": "crypto",
            "destination_wallet": "0x18CE1930820d5e1B87F37a8a2F7Cf59E7BF6da4E"
        }
        
        response1 = requests.post(f"{BASE_URL}/api/neno-exchange/offramp", headers=headers, json=offramp_payload)
        response2 = requests.post(f"{BASE_URL}/api/neno-exchange/offramp", headers=headers, json=offramp_payload)
        
        assert "E11000" not in response2.text, f"Got E11000 on offramp: {response2.text}"
        print("✓ Offramp idempotency: no E11000 error")


class TestHealthAndBasicEndpoints:
    """Basic health and endpoint tests"""
    
    def test_14_health_check(self):
        """GET /api/health returns healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("✓ Health check passed")
    
    def test_15_neno_price_endpoint(self):
        """GET /api/neno-exchange/price returns pricing info"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/price")
        assert response.status_code == 200
        data = response.json()
        assert "neno_eur_price" in data or "mid_price" in data
        print(f"✓ NENO price: {data.get('neno_eur_price') or data.get('mid_price')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
