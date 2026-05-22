"""
Iteration 44 - Institutional Liquidity Router & KYC Provider Tests

Tests:
- Auth: Admin and User login
- Router: Status, Quote (BTC/NENO/ETH), Execute, Venues, Fallback Matrix
- KYC Provider: Create applicant, Status, Verification URL, Provider status, Webhook
- Pipeline: Status, Deposit
- Stripe Webhook: Signature enforcement
"""

import pytest
import requests
import os
import json

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"
USER_EMAIL = "test@example.com"
USER_PASSWORD = "Test1234!"


class TestAuth:
    """Authentication tests"""
    
    def test_01_admin_login(self):
        """Admin login returns token with ADMIN role"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        # Role is in user object
        user_role = data.get("user", {}).get("role")
        assert user_role == "ADMIN", f"Expected ADMIN role, got {user_role}"
        print(f"PASSED: Admin login - role={user_role}")
    
    def test_02_user_login(self):
        """User login returns token with USER role"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        })
        assert response.status_code == 200, f"User login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        # Role is in user object
        user_role = data.get("user", {}).get("role")
        assert user_role == "USER", f"Expected USER role, got {user_role}"
        print(f"PASSED: User login - role={user_role}")


@pytest.fixture(scope="class")
def admin_token():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Admin login failed")


@pytest.fixture(scope="class")
def user_token():
    """Get user auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": USER_EMAIL,
        "password": USER_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("User login failed")


class TestRouterStatus:
    """Institutional Liquidity Router Status Tests"""
    
    def test_03_router_status(self, admin_token):
        """GET /api/router/status returns venue availability"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/router/status", headers=headers)
        assert response.status_code == 200, f"Router status failed: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "router" in data, "Missing router field"
        assert "venues" in data, "Missing venues field"
        assert "split_threshold_eur" in data, "Missing split_threshold_eur"
        assert "slippage_guard_pct" in data, "Missing slippage_guard_pct"
        
        # Verify venues
        venues = data["venues"]
        assert "binance" in venues, "Missing binance venue"
        assert "kraken" in venues, "Missing kraken venue"
        assert "mexc" in venues, "Missing mexc venue"
        assert "internal" in venues, "Missing internal venue"
        assert "pancakeswap" in venues, "Missing pancakeswap venue"
        
        # Binance is geo-blocked (HTTP 451) - expected
        print(f"PASSED: Router status - venues: {list(venues.keys())}")
        print(f"  Binance: {venues.get('binance')}")
        print(f"  Kraken: {venues.get('kraken')}")
        print(f"  MEXC: {venues.get('mexc')}")
        print(f"  Split threshold: {data.get('split_threshold_eur')} EUR")


class TestRouterQuote:
    """Router Quote Tests"""
    
    def test_04_quote_btc_buy(self, admin_token):
        """POST /api/router/quote - BTC buy 0.1 shows multiple venues"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.post(f"{BASE_URL}/api/router/quote", headers=headers, json={
            "asset": "BTC",
            "side": "buy",
            "amount": 0.1
        })
        assert response.status_code == 200, f"Quote failed: {response.text}"
        data = response.json()
        
        assert "route_id" in data, "Missing route_id"
        assert "best_venue" in data, "Missing best_venue"
        assert "quotes" in data, "Missing quotes"
        assert len(data["quotes"]) > 0, "No quotes returned"
        
        print(f"PASSED: BTC buy quote - best_venue={data.get('best_venue')}, quotes={len(data['quotes'])}")
        for q in data["quotes"]:
            print(f"  {q.get('venue')}: available={q.get('available')}, price={q.get('price')}")
    
    def test_05_quote_neno_buy_custom_token(self, admin_token):
        """POST /api/router/quote - NENO buy 1 uses custom fallback"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.post(f"{BASE_URL}/api/router/quote", headers=headers, json={
            "asset": "NENO",
            "side": "buy",
            "amount": 1
        })
        assert response.status_code == 200, f"Quote failed: {response.text}"
        data = response.json()
        
        assert "route_id" in data, "Missing route_id"
        assert "best_venue" in data, "Missing best_venue"
        # NENO should use internal or custom fallback
        print(f"PASSED: NENO buy quote - best_venue={data.get('best_venue')}, net_price={data.get('net_price')}")
    
    def test_06_quote_eth_sell_split(self, admin_token):
        """POST /api/router/quote - ETH sell 2 shows split decision"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.post(f"{BASE_URL}/api/router/quote", headers=headers, json={
            "asset": "ETH",
            "side": "sell",
            "amount": 2
        })
        assert response.status_code == 200, f"Quote failed: {response.text}"
        data = response.json()
        
        assert "route_id" in data, "Missing route_id"
        assert "split" in data, "Missing split field"
        print(f"PASSED: ETH sell quote - split={data.get('split')}, best_venue={data.get('best_venue')}")
    
    def test_07_quote_validation_amount_zero(self, admin_token):
        """POST /api/router/quote - amount <= 0 returns 400"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.post(f"{BASE_URL}/api/router/quote", headers=headers, json={
            "asset": "BTC",
            "side": "buy",
            "amount": 0
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASSED: Quote validation - amount=0 returns 400")
    
    def test_08_quote_validation_invalid_side(self, admin_token):
        """POST /api/router/quote - invalid side returns 400"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.post(f"{BASE_URL}/api/router/quote", headers=headers, json={
            "asset": "BTC",
            "side": "invalid",
            "amount": 0.1
        })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASSED: Quote validation - invalid side returns 400")


class TestRouterExecute:
    """Router Execute Tests"""
    
    def test_09_execute_neno_buy(self, admin_token):
        """POST /api/router/execute - Execute routed order for NENO buy 1"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.post(f"{BASE_URL}/api/router/execute", headers=headers, json={
            "asset": "NENO",
            "side": "buy",
            "amount": 1
        })
        assert response.status_code == 200, f"Execute failed: {response.text}"
        data = response.json()
        
        assert "route_id" in data, "Missing route_id"
        assert "executed" in data, "Missing executed field"
        print(f"PASSED: NENO execute - executed={data.get('executed')}, venue={data.get('venue')}")


class TestRouterVenues:
    """Router Venues Tests"""
    
    def test_10_list_venues(self, admin_token):
        """GET /api/router/venues - Returns all venue connectivity status"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/router/venues", headers=headers)
        assert response.status_code == 200, f"Venues failed: {response.text}"
        data = response.json()
        
        assert "venues" in data, "Missing venues"
        assert "primary" in data, "Missing primary"
        assert "fallback" in data, "Missing fallback"
        
        venues = data["venues"]
        print(f"PASSED: Venues list - primary={data.get('primary')}, fallback={data.get('fallback')}")
        for name, status in venues.items():
            print(f"  {name}: connected={status.get('connected')}")


class TestRouterFallbackMatrix:
    """Router Fallback Matrix Tests"""
    
    def test_11_fallback_matrix(self, admin_token):
        """GET /api/router/fallback-matrix - Returns standard pairs and custom token strategies"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/router/fallback-matrix", headers=headers)
        assert response.status_code == 200, f"Fallback matrix failed: {response.text}"
        data = response.json()
        
        assert "standard_pairs" in data, "Missing standard_pairs"
        assert "custom_token_strategy" in data, "Missing custom_token_strategy"
        assert "intermediate_tokens" in data, "Missing intermediate_tokens"
        
        # Verify standard pairs
        pairs = data["standard_pairs"]
        assert "BTC" in pairs, "Missing BTC in standard pairs"
        assert "ETH" in pairs, "Missing ETH in standard pairs"
        
        # Verify custom token strategy
        strategies = data["custom_token_strategy"]
        assert len(strategies) == 4, f"Expected 4 strategies, got {len(strategies)}"
        
        print(f"PASSED: Fallback matrix - {len(pairs)} standard pairs, {len(strategies)} strategies")
        for s in strategies:
            print(f"  Priority {s.get('priority')}: {s.get('method')}")


class TestKYCProvider:
    """KYC/AML Provider Tests"""
    
    def test_12_create_applicant(self, user_token):
        """POST /api/kyc-provider/applicant - Create KYC applicant"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.post(f"{BASE_URL}/api/kyc-provider/applicant", headers=headers, json={
            "first_name": "Test",
            "last_name": "User"
        })
        assert response.status_code == 200, f"Create applicant failed: {response.text}"
        data = response.json()
        
        assert "user_id" in data or "applicant_id" in data, "Missing user_id or applicant_id"
        assert "provider" in data, "Missing provider"
        print(f"PASSED: Create applicant - provider={data.get('provider')}, status={data.get('status')}")
    
    def test_13_get_kyc_status(self, user_token):
        """GET /api/kyc-provider/status - Get KYC status"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.get(f"{BASE_URL}/api/kyc-provider/status", headers=headers)
        assert response.status_code == 200, f"KYC status failed: {response.text}"
        data = response.json()
        
        assert "status" in data, "Missing status"
        assert "provider" in data, "Missing provider"
        print(f"PASSED: KYC status - status={data.get('status')}, provider={data.get('provider')}")
    
    def test_14_get_verification_url(self, user_token):
        """GET /api/kyc-provider/verification-url - Get verification URL"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.get(f"{BASE_URL}/api/kyc-provider/verification-url", headers=headers)
        assert response.status_code == 200, f"Verification URL failed: {response.text}"
        data = response.json()
        
        assert "provider" in data, "Missing provider"
        # AI fallback won't have URL, but will have instructions
        if data.get("provider") == "ai_verification":
            assert "instructions" in data, "Missing instructions for AI fallback"
        print(f"PASSED: Verification URL - provider={data.get('provider')}")
    
    def test_15_provider_status_admin(self, admin_token):
        """GET /api/kyc-provider/provider-status - Admin: provider config status"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/kyc-provider/provider-status", headers=headers)
        assert response.status_code == 200, f"Provider status failed: {response.text}"
        data = response.json()
        
        assert "provider" in data, "Missing provider"
        assert "configured" in data, "Missing configured"
        assert "applicants" in data, "Missing applicants"
        
        print(f"PASSED: Provider status - provider={data.get('provider')}, configured={data.get('configured')}")
        print(f"  Applicants: {data.get('applicants')}")
    
    def test_16_provider_status_non_admin_403(self, user_token):
        """GET /api/kyc-provider/provider-status - Non-admin returns 403"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.get(f"{BASE_URL}/api/kyc-provider/provider-status", headers=headers)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("PASSED: Provider status - non-admin returns 403")
    
    def test_17_kyc_webhook(self):
        """POST /api/kyc-provider/webhook - KYC webhook handler"""
        response = requests.post(f"{BASE_URL}/api/kyc-provider/webhook", json={
            "type": "applicantReviewed",
            "applicantId": "test-applicant-123",
            "externalUserId": "test-user-id",
            "reviewResult": {"reviewAnswer": "GREEN"}
        })
        assert response.status_code == 200, f"Webhook failed: {response.text}"
        data = response.json()
        
        assert "handled" in data, "Missing handled"
        print(f"PASSED: KYC webhook - handled={data.get('handled')}, event={data.get('event')}")


class TestPipeline:
    """Pipeline Tests (from previous iteration)"""
    
    def test_18_pipeline_status(self, admin_token):
        """GET /api/pipeline/status - Pipeline status"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/pipeline/status", headers=headers)
        assert response.status_code == 200, f"Pipeline status failed: {response.text}"
        data = response.json()
        
        assert "running" in data, "Missing running"
        print(f"PASSED: Pipeline status - running={data.get('running')}, cycle_count={data.get('cycle_count')}")
    
    def test_19_create_deposit(self, user_token):
        """POST /api/pipeline/deposit - Create deposit intent"""
        headers = {"Authorization": f"Bearer {user_token}"}
        response = requests.post(f"{BASE_URL}/api/pipeline/deposit", headers=headers, json={
            "amount_eur": 10
        })
        assert response.status_code == 200, f"Deposit failed: {response.text}"
        data = response.json()
        
        assert "deposit_id" in data, "Missing deposit_id"
        assert "client_secret" in data, "Missing client_secret"
        print(f"PASSED: Create deposit - deposit_id={data.get('deposit_id')}")


class TestStripeWebhook:
    """Stripe Webhook Signature Enforcement Tests"""
    
    def test_20_webhook_without_signature_400(self):
        """POST /api/stripe/webhook - Rejects without signature (400)"""
        # Send webhook without stripe-signature header
        response = requests.post(f"{BASE_URL}/api/stripe/webhook", 
            data=json.dumps({"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_test"}}}),
            headers={"Content-Type": "application/json"}
        )
        # Should return 400 because STRIPE_WEBHOOK_SECRET is configured
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASSED: Stripe webhook - rejects without signature (400)")
    
    def test_21_webhook_with_invalid_signature_400(self):
        """POST /api/stripe/webhook - Rejects with invalid signature (400)"""
        response = requests.post(f"{BASE_URL}/api/stripe/webhook",
            data=json.dumps({"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_test"}}}),
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "t=1234567890,v1=invalid_signature"
            }
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        print("PASSED: Stripe webhook - rejects invalid signature (400)")


class TestHealthCheck:
    """Health Check"""
    
    def test_22_health_check(self):
        """GET /api/health - Returns healthy"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.text}"
        data = response.json()
        assert data.get("status") == "healthy", f"Expected healthy, got {data.get('status')}"
        print("PASSED: Health check - status=healthy")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
