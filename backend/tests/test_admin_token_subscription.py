"""
Backend Tests for Admin Dashboard, Token Management, and Subscription System
NeoNoble Ramp - Enterprise Fintech Platform

Tests cover:
- Admin authentication and users endpoint
- Token creation, listing, admin actions (approve/reject)
- Subscription plans (6 plans), subscription creation
- Token stats and subscription stats for admin dashboard
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"
TEST_USER_EMAIL = "testchart@example.com"
TEST_USER_PASSWORD = "Test1234!"


class TestAdminAuthentication:
    """Admin authentication and users endpoint tests"""
    
    def test_admin_login_success(self):
        """Test admin login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert "token" in data
        assert data["user"]["role"] == "ADMIN"
        assert data["user"]["email"] == ADMIN_EMAIL
        print(f"✓ Admin login successful, role={data['user']['role']}")
    
    def test_admin_users_list(self):
        """Test admin users list endpoint"""
        # Login as admin
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get users list
        response = requests.get(f"{BASE_URL}/api/auth/admin/users", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "users" in data
        assert "total" in data
        assert data["total"] >= 1  # At least admin user
        
        # Verify admin user is in list
        admin_found = any(u["email"] == ADMIN_EMAIL for u in data["users"])
        assert admin_found, "Admin user should be in users list"
        print(f"✓ Admin users list returned {data['total']} users")
    
    def test_admin_users_access_denied_for_regular_user(self):
        """Test that regular users cannot access admin users endpoint"""
        # Login as regular user
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        if login_res.status_code != 200:
            pytest.skip("Test user not available")
        
        token = login_res.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Try to access admin endpoint
        response = requests.get(f"{BASE_URL}/api/auth/admin/users", headers=headers)
        assert response.status_code == 403
        print("✓ Regular user correctly denied access to admin users endpoint")


class TestTokenManagement:
    """Token CRUD and admin actions tests"""
    
    @pytest.fixture
    def admin_headers(self):
        """Get admin auth headers"""
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = login_res.json()["token"]
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    def test_token_list_returns_data(self, admin_headers):
        """Test that token list endpoint returns proper structure"""
        response = requests.get(f"{BASE_URL}/api/tokens/list", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "tokens" in data
        assert "total" in data
        assert "page" in data
        print(f"✓ Token list returned {data['total']} tokens")
    
    def test_token_list_has_mytoken_pending(self, admin_headers):
        """Test that MYTOKEN exists with pending status"""
        response = requests.get(f"{BASE_URL}/api/tokens/list", headers=admin_headers)
        assert response.status_code == 200
        tokens = response.json()["tokens"]
        
        mytoken = next((t for t in tokens if t["symbol"] == "MYTOKEN"), None)
        if mytoken:
            assert mytoken["status"] == "pending"
            assert mytoken["name"] == "MyToken"
            print(f"✓ MYTOKEN found with status={mytoken['status']}")
        else:
            print("✓ MYTOKEN not found (may have been approved/processed)")
    
    def test_token_creation(self, admin_headers):
        """Test creating a new token"""
        unique_id = str(uuid.uuid4())[:6].upper()
        token_data = {
            "name": f"TestToken{unique_id}",
            "symbol": f"TT{unique_id}",
            "description": "Test token for automated testing",
            "total_supply": 500000,
            "initial_price": 2.50,
            "chain": "ethereum",
            "decimals": 18
        }
        
        response = requests.post(f"{BASE_URL}/api/tokens/create", headers=admin_headers, json=token_data)
        assert response.status_code == 200
        data = response.json()
        
        assert data["name"] == token_data["name"]
        assert data["symbol"] == token_data["symbol"]
        assert data["status"] == "pending"
        assert data["chain"] == "ethereum"
        assert data["total_supply"] == 500000
        assert data["current_price"] == 2.50
        assert data["creation_fee"] == 100.0
        print(f"✓ Token created: {data['symbol']} with status={data['status']}")
        
        return data["id"], data["symbol"]
    
    def test_token_admin_approve(self, admin_headers):
        """Test approving a token"""
        # First create a token
        unique_id = str(uuid.uuid4())[:6].upper()
        create_res = requests.post(f"{BASE_URL}/api/tokens/create", headers=admin_headers, json={
            "name": f"ApproveTest{unique_id}",
            "symbol": f"AT{unique_id}",
            "total_supply": 100000,
            "initial_price": 1.0,
            "chain": "bsc"
        })
        token_id = create_res.json()["id"]
        
        # Approve the token
        response = requests.post(
            f"{BASE_URL}/api/tokens/{token_id}/admin-action",
            headers=admin_headers,
            json={"action": "approve"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["new_status"] == "approved"
        print(f"✓ Token {token_id[:8]}... approved successfully")
    
    def test_token_admin_go_live(self, admin_headers):
        """Test making an approved token go live"""
        # Create and approve a token
        unique_id = str(uuid.uuid4())[:6].upper()
        create_res = requests.post(f"{BASE_URL}/api/tokens/create", headers=admin_headers, json={
            "name": f"LiveTest{unique_id}",
            "symbol": f"LT{unique_id}",
            "total_supply": 50000,
            "initial_price": 0.5,
            "chain": "polygon"
        })
        token_id = create_res.json()["id"]
        
        # Approve first
        requests.post(
            f"{BASE_URL}/api/tokens/{token_id}/admin-action",
            headers=admin_headers,
            json={"action": "approve"}
        )
        
        # Then go live
        response = requests.post(
            f"{BASE_URL}/api/tokens/{token_id}/admin-action",
            headers=admin_headers,
            json={"action": "go_live"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["new_status"] == "live"
        print(f"✓ Token {token_id[:8]}... is now LIVE")
    
    def test_token_stats_overview(self, admin_headers):
        """Test token stats overview for admin dashboard"""
        response = requests.get(f"{BASE_URL}/api/tokens/stats/overview", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "tokens" in data
        assert "total" in data["tokens"]
        assert "pending" in data["tokens"]
        assert "approved" in data["tokens"]
        assert "live" in data["tokens"]
        
        assert "listings" in data
        assert "trading_pairs" in data
        
        assert "fees" in data
        assert data["fees"]["token_creation"] == 100
        assert data["fees"]["listing_standard"] == 500
        assert data["fees"]["listing_premium"] == 2000
        print(f"✓ Token stats: total={data['tokens']['total']}, pending={data['tokens']['pending']}, live={data['tokens']['live']}")


class TestTokenListings:
    """Token listing request tests"""
    
    @pytest.fixture
    def admin_headers(self):
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = login_res.json()["token"]
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    def test_listings_list_returns_structure(self, admin_headers):
        """Test that listings list endpoint returns proper structure"""
        response = requests.get(f"{BASE_URL}/api/tokens/listings/list", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "listings" in data
        assert "total" in data
        print(f"✓ Listings list returned {data['total']} listings")
    
    def test_create_listing_request(self, admin_headers):
        """Test creating a listing request for an approved token"""
        # First create and approve a token
        unique_id = str(uuid.uuid4())[:6].upper()
        create_res = requests.post(f"{BASE_URL}/api/tokens/create", headers=admin_headers, json={
            "name": f"ListingTest{unique_id}",
            "symbol": f"LST{unique_id}",
            "total_supply": 200000,
            "initial_price": 3.0,
            "chain": "arbitrum"
        })
        token_id = create_res.json()["id"]
        
        # Approve the token
        requests.post(
            f"{BASE_URL}/api/tokens/{token_id}/admin-action",
            headers=admin_headers,
            json={"action": "approve"}
        )
        
        # Create listing request
        response = requests.post(f"{BASE_URL}/api/tokens/listings/create", headers=admin_headers, json={
            "token_id": token_id,
            "listing_type": "standard",
            "requested_pairs": ["EUR", "USD", "USDT"]
        })
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "pending"
        assert data["listing_fee"] == 500.0  # Standard fee
        assert "EUR" in data["requested_pairs"]
        print(f"✓ Listing request created for token {token_id[:8]}... with fee=€{data['listing_fee']}")


class TestSubscriptionPlans:
    """Subscription plans tests"""
    
    @pytest.fixture
    def admin_headers(self):
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = login_res.json()["token"]
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    def test_subscription_plans_list_returns_6_plans(self, admin_headers):
        """Test that 6 subscription plans are available"""
        response = requests.get(f"{BASE_URL}/api/subscriptions/plans/list", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        plans = data["plans"]
        assert len(plans) == 6, f"Expected 6 plans, got {len(plans)}"
        
        # Verify plan codes
        expected_codes = ["free", "pro_trader", "premium", "developer_basic", "developer_pro", "enterprise"]
        actual_codes = [p["code"] for p in plans]
        for code in expected_codes:
            assert code in actual_codes, f"Plan {code} not found"
        
        print(f"✓ All 6 subscription plans present: {actual_codes}")
    
    def test_subscription_plans_pricing_correct(self, admin_headers):
        """Test that plan pricing is correct"""
        response = requests.get(f"{BASE_URL}/api/subscriptions/plans/list", headers=admin_headers)
        plans = {p["code"]: p for p in response.json()["plans"]}
        
        # Verify key prices
        assert plans["free"]["price_monthly"] == 0.0
        assert plans["pro_trader"]["price_monthly"] == 29.99
        assert plans["premium"]["price_monthly"] == 99.99
        assert plans["developer_basic"]["price_monthly"] == 49.99
        assert plans["developer_pro"]["price_monthly"] == 199.99
        assert plans["enterprise"]["price_monthly"] == 999.99
        
        print("✓ All subscription plan prices verified")
    
    def test_subscription_plans_yearly_discount(self, admin_headers):
        """Test that yearly plans have discount (~17%)"""
        response = requests.get(f"{BASE_URL}/api/subscriptions/plans/list", headers=admin_headers)
        plans = response.json()["plans"]
        
        for plan in plans:
            if plan["price_monthly"] > 0:
                yearly_price = plan["price_yearly"]
                monthly_equivalent = plan["price_monthly"] * 12
                if yearly_price > 0:
                    discount = (monthly_equivalent - yearly_price) / monthly_equivalent
                    assert discount > 0.1, f"Plan {plan['code']} should have yearly discount"
        
        print("✓ Yearly pricing discount verified")
    
    def test_subscription_admin_stats(self, admin_headers):
        """Test subscription admin stats endpoint"""
        response = requests.get(f"{BASE_URL}/api/subscriptions/admin/stats", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "total_subscriptions" in data
        assert "by_status" in data
        assert "monthly_recurring_revenue" in data
        assert data["currency"] == "EUR"
        
        print(f"✓ Subscription stats: total={data['total_subscriptions']}, MRR=€{data['monthly_recurring_revenue']}")
    
    def test_subscribe_to_plan(self, admin_headers):
        """Test subscribing to a plan"""
        # Get plans
        plans_res = requests.get(f"{BASE_URL}/api/subscriptions/plans/list", headers=admin_headers)
        plans = plans_res.json()["plans"]
        pro_trader = next((p for p in plans if p["code"] == "pro_trader"), None)
        
        if not pro_trader:
            pytest.skip("Pro Trader plan not found")
        
        # Check if admin already has subscription
        my_sub_res = requests.get(f"{BASE_URL}/api/subscriptions/my-subscription", headers=admin_headers)
        if my_sub_res.status_code == 200 and my_sub_res.json() is not None:
            # Cancel existing subscription first
            requests.post(f"{BASE_URL}/api/subscriptions/cancel", headers=admin_headers)
        
        # Subscribe to Pro Trader (monthly)
        response = requests.post(f"{BASE_URL}/api/subscriptions/subscribe", headers=admin_headers, json={
            "plan_id": pro_trader["id"],
            "billing_cycle": "monthly"
        })
        assert response.status_code == 200
        data = response.json()
        
        assert data["plan_name"] == "Pro Trader"
        assert data["status"] == "active"
        assert data["billing_cycle"] == "monthly"
        assert data["amount_paid"] == 29.99
        print(f"✓ Subscribed to {data['plan_name']} for €{data['amount_paid']}/month")
        
        # Clean up - cancel subscription
        requests.post(f"{BASE_URL}/api/subscriptions/cancel", headers=admin_headers)


class TestSubscriptionAdminList:
    """Subscription admin list tests"""
    
    @pytest.fixture
    def admin_headers(self):
        login_res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = login_res.json()["token"]
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    
    def test_admin_subscriptions_list(self, admin_headers):
        """Test admin subscriptions list endpoint"""
        response = requests.get(f"{BASE_URL}/api/subscriptions/admin/list", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "subscriptions" in data
        assert "total" in data
        assert "page" in data
        print(f"✓ Admin subscriptions list: {data['total']} subscriptions")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
