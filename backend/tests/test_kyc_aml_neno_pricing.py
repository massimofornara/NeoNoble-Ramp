"""
Test KYC/AML Compliance Layer and Dynamic NENO Pricing
Tests for iteration 11 - New features:
- KYC status endpoint
- KYC submission
- KYC admin review (pending list, approve/reject)
- AML alerts and stats
- Dynamic NENO pricing based on order book pressure
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


class TestKYCStatusEndpoint:
    """Test GET /api/kyc/status - KYC status for authenticated user"""
    
    @pytest.fixture
    def user_token(self):
        """Get auth token for test user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip(f"Login failed for test user: {response.text}")
    
    def test_kyc_status_returns_tier_info(self, user_token):
        """GET /api/kyc/status returns tier info"""
        response = requests.get(
            f"{BASE_URL}/api/kyc/status",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify required fields
        assert "tier" in data, "Missing 'tier' field"
        assert "tier_label" in data, "Missing 'tier_label' field"
        assert "status" in data, "Missing 'status' field"
        assert "daily_limit" in data, "Missing 'daily_limit' field"
        assert "daily_used" in data, "Missing 'daily_used' field"
        assert "can_trade" in data, "Missing 'can_trade' field"
        assert "can_withdraw" in data, "Missing 'can_withdraw' field"
        
        # Verify tier is valid (0-3)
        assert data["tier"] in [0, 1, 2, 3], f"Invalid tier: {data['tier']}"
        
        # Verify tier_label matches tier
        tier_labels = {0: "Non Verificato", 1: "Base", 2: "Verificato", 3: "Premium"}
        assert data["tier_label"] == tier_labels.get(data["tier"]), f"Tier label mismatch"
        
        print(f"KYC Status: Tier {data['tier']} ({data['tier_label']}), Status: {data['status']}")
    
    def test_kyc_status_requires_auth(self):
        """GET /api/kyc/status requires authentication"""
        response = requests.get(f"{BASE_URL}/api/kyc/status")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


class TestKYCSubmission:
    """Test POST /api/kyc/submit - KYC document submission"""
    
    @pytest.fixture
    def user_token(self):
        """Get auth token for test user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip(f"Login failed for test user: {response.text}")
    
    def test_kyc_submit_creates_pending_application(self, user_token):
        """POST /api/kyc/submit creates pending application"""
        # Note: testchart@example.com already has a pending KYC submission
        # This test verifies the endpoint behavior
        kyc_data = {
            "first_name": "Test",
            "last_name": "User",
            "date_of_birth": "1990-01-15",
            "nationality": "IT",
            "address_line1": "Via Roma 123",
            "address_city": "Milano",
            "address_country": "IT",
            "address_postal": "20100",
            "tax_id": "TSTSSR90A15F205X",
            "document_type": "id_card",
            "document_number": "CA12345678"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/kyc/submit",
            headers={"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"},
            json=kyc_data
        )
        
        # Either 200 (success) or 400 (already pending) is acceptable
        assert response.status_code in [200, 400], f"Expected 200/400, got {response.status_code}: {response.text}"
        
        data = response.json()
        if response.status_code == 200:
            assert "message" in data, "Missing 'message' field"
            assert data.get("status") == "pending", f"Expected status 'pending', got {data.get('status')}"
            print(f"KYC Submission: {data['message']}")
        else:
            # Already pending
            assert "detail" in data, "Missing 'detail' field for error"
            print(f"KYC Submission blocked (expected): {data['detail']}")
    
    def test_kyc_submit_requires_auth(self):
        """POST /api/kyc/submit requires authentication"""
        response = requests.post(f"{BASE_URL}/api/kyc/submit", json={
            "first_name": "Test",
            "last_name": "User",
            "date_of_birth": "1990-01-15",
            "nationality": "IT",
            "address_line1": "Via Roma 123",
            "address_city": "Milano",
            "address_country": "IT",
            "address_postal": "20100",
            "document_type": "id_card",
            "document_number": "CA12345678"
        })
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


class TestKYCAdminEndpoints:
    """Test KYC admin endpoints - requires admin role"""
    
    @pytest.fixture
    def admin_token(self):
        """Get auth token for admin user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip(f"Admin login failed: {response.text}")
    
    @pytest.fixture
    def user_token(self):
        """Get auth token for regular user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip(f"User login failed: {response.text}")
    
    def test_admin_pending_list(self, admin_token):
        """GET /api/kyc/admin/pending returns pending KYC applications"""
        response = requests.get(
            f"{BASE_URL}/api/kyc/admin/pending",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "pending" in data, "Missing 'pending' field"
        assert "total" in data, "Missing 'total' field"
        assert isinstance(data["pending"], list), "'pending' should be a list"
        
        print(f"Admin Pending KYC: {data['total']} applications")
        
        # If there are pending applications, verify structure
        if data["pending"]:
            app = data["pending"][0]
            assert "user_id" in app, "Missing 'user_id' in pending application"
            assert "first_name" in app, "Missing 'first_name' in pending application"
            assert "last_name" in app, "Missing 'last_name' in pending application"
            print(f"First pending: {app.get('first_name')} {app.get('last_name')}")
    
    def test_admin_pending_requires_admin_role(self, user_token):
        """GET /api/kyc/admin/pending requires admin role"""
        response = requests.get(
            f"{BASE_URL}/api/kyc/admin/pending",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
    
    def test_admin_review_approve_action(self, admin_token):
        """POST /api/kyc/admin/review with approve action"""
        # First get pending list to find a user to approve
        pending_response = requests.get(
            f"{BASE_URL}/api/kyc/admin/pending",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        
        if pending_response.status_code != 200:
            pytest.skip("Could not get pending list")
        
        pending = pending_response.json().get("pending", [])
        if not pending:
            pytest.skip("No pending KYC applications to test review")
        
        user_id = pending[0]["user_id"]
        current_tier = pending[0].get("tier", 0)
        
        # Approve the application
        response = requests.post(
            f"{BASE_URL}/api/kyc/admin/review",
            headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
            json={
                "user_id": user_id,
                "action": "approve",
                "new_tier": min(current_tier + 1, 3)
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Missing 'message' field"
        assert data.get("new_status") == "approved", f"Expected 'approved', got {data.get('new_status')}"
        print(f"Admin Review: {data['message']}")


class TestAMLEndpoints:
    """Test AML monitoring endpoints"""
    
    @pytest.fixture
    def admin_token(self):
        """Get auth token for admin user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip(f"Admin login failed: {response.text}")
    
    @pytest.fixture
    def user_token(self):
        """Get auth token for regular user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip(f"User login failed: {response.text}")
    
    def test_aml_alerts_endpoint(self, admin_token):
        """GET /api/kyc/aml/alerts returns AML alerts"""
        response = requests.get(
            f"{BASE_URL}/api/kyc/aml/alerts",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "alerts" in data, "Missing 'alerts' field"
        assert "total" in data, "Missing 'total' field"
        assert isinstance(data["alerts"], list), "'alerts' should be a list"
        
        print(f"AML Alerts: {data['total']} total")
        
        # If there are alerts, verify structure
        if data["alerts"]:
            alert = data["alerts"][0]
            assert "id" in alert, "Missing 'id' in alert"
            assert "type" in alert, "Missing 'type' in alert"
            assert "status" in alert, "Missing 'status' in alert"
    
    def test_aml_stats_endpoint(self, admin_token):
        """GET /api/kyc/aml/stats returns AML statistics"""
        response = requests.get(
            f"{BASE_URL}/api/kyc/aml/stats",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "open_alerts" in data, "Missing 'open_alerts' field"
        assert "escalated" in data, "Missing 'escalated' field"
        assert "blocked_users" in data, "Missing 'blocked_users' field"
        assert "total_alerts" in data, "Missing 'total_alerts' field"
        
        print(f"AML Stats: {data['open_alerts']} open, {data['escalated']} escalated, {data['blocked_users']} blocked")
    
    def test_aml_alerts_requires_admin(self, user_token):
        """GET /api/kyc/aml/alerts requires admin role"""
        response = requests.get(
            f"{BASE_URL}/api/kyc/aml/alerts",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
    
    def test_aml_stats_requires_admin(self, user_token):
        """GET /api/kyc/aml/stats requires admin role"""
        response = requests.get(
            f"{BASE_URL}/api/kyc/aml/stats",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"


class TestDynamicNENOPricing:
    """Test Dynamic NENO pricing based on order book pressure"""
    
    def test_neno_price_endpoint(self):
        """GET /api/neno-exchange/price returns dynamic price with volume data"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/price")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify required fields for dynamic pricing
        assert "neno_eur_price" in data, "Missing 'neno_eur_price' field"
        assert "base_price" in data, "Missing 'base_price' field"
        assert "price_shift" in data, "Missing 'price_shift' field"
        assert "shift_pct" in data, "Missing 'shift_pct' field"
        assert "buy_volume_24h" in data, "Missing 'buy_volume_24h' field"
        assert "sell_volume_24h" in data, "Missing 'sell_volume_24h' field"
        assert "net_pressure" in data, "Missing 'net_pressure' field"
        assert "pricing_model" in data, "Missing 'pricing_model' field"
        assert "max_deviation" in data, "Missing 'max_deviation' field"
        
        # Verify base price is 10000 EUR
        assert data["base_price"] == 10000.0, f"Expected base_price 10000, got {data['base_price']}"
        
        # Verify pricing model is dynamic
        assert data["pricing_model"] == "dynamic_orderbook", f"Expected 'dynamic_orderbook', got {data['pricing_model']}"
        
        # Verify max deviation is 5%
        assert "5" in data["max_deviation"], f"Expected max_deviation to contain '5', got {data['max_deviation']}"
        
        # Verify price is within 5% of base
        price = data["neno_eur_price"]
        assert 9500 <= price <= 10500, f"Price {price} outside 5% deviation from base 10000"
        
        print(f"NENO Price: EUR {price} (base: {data['base_price']}, shift: {data['shift_pct']}%)")
        print(f"24h Volume - Buy: {data['buy_volume_24h']}, Sell: {data['sell_volume_24h']}, Net: {data['net_pressure']}")
    
    def test_neno_quote_uses_dynamic_pricing(self):
        """GET /api/neno-exchange/quote uses dynamic pricing"""
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/quote",
            params={"direction": "buy", "asset": "EUR", "neno_amount": 1.0}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify quote includes dynamic pricing info
        assert "neno_eur_price" in data, "Missing 'neno_eur_price' field"
        assert "base_price" in data, "Missing 'base_price' field"
        assert "price_shift_pct" in data, "Missing 'price_shift_pct' field"
        assert "rate" in data, "Missing 'rate' field"
        assert "total_cost" in data, "Missing 'total_cost' field"
        assert "fee" in data, "Missing 'fee' field"
        
        # Verify base price
        assert data["base_price"] == 10000.0, f"Expected base_price 10000, got {data['base_price']}"
        
        print(f"Quote: 1 NENO = EUR {data['neno_eur_price']} (shift: {data['price_shift_pct']}%)")
        print(f"Total cost: EUR {data['total_cost']} (fee: {data['fee']})")
    
    def test_neno_quote_sell_direction(self):
        """GET /api/neno-exchange/quote for sell direction"""
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/quote",
            params={"direction": "sell", "asset": "EUR", "neno_amount": 0.5}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["direction"] == "sell", f"Expected direction 'sell', got {data['direction']}"
        assert "net_receive" in data, "Missing 'net_receive' field for sell quote"
        assert "neno_eur_price" in data, "Missing 'neno_eur_price' field"
        
        print(f"Sell Quote: 0.5 NENO -> EUR {data['net_receive']} (price: {data['neno_eur_price']})")


class TestNENOExchangeIntegration:
    """Test NENO exchange buy/sell with dynamic pricing"""
    
    @pytest.fixture
    def user_token(self):
        """Get auth token for test user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        if response.status_code == 200:
            return response.json().get("token")
        pytest.skip(f"Login failed for test user: {response.text}")
    
    def test_neno_transactions_endpoint(self, user_token):
        """GET /api/neno-exchange/transactions returns transaction history"""
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/transactions",
            headers={"Authorization": f"Bearer {user_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "transactions" in data, "Missing 'transactions' field"
        assert "total" in data, "Missing 'total' field"
        
        print(f"NENO Transactions: {data['total']} total")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
