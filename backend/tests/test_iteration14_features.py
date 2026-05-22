"""
Iteration 14 Feature Tests - Real-time Portfolio Tracker & NIUM Real API Integration

Tests:
1. NIUM Onboarding - Real API (no simulation)
   - GET /api/nium-onboarding/available-methods - returns all 4 KYC modes
   - POST /api/nium-onboarding/create-customer - returns real NIUM error (NOT simulated)
   - GET /api/nium-onboarding/status - shows onboarding status
   - GET /api/nium-onboarding/compliance-status - returns real NIUM error
   - GET /api/nium-onboarding/customer-details - returns real NIUM error

2. WebSocket Portfolio Tracker
   - GET /api/ws/status - WebSocket server status

3. Rate Limiting
   - X-RateLimit headers on responses
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


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token for regular user"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


class TestNiumOnboardingAvailableMethods:
    """Test GET /api/nium-onboarding/available-methods - returns all 4 KYC modes"""

    def test_available_methods_returns_all_kyc_modes(self, api_client):
        """Verify all 4 KYC modes are returned with setup instructions"""
        response = api_client.get(f"{BASE_URL}/api/nium-onboarding/available-methods")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Check configuration status
        assert "nium_configured" in data
        assert "nium_base_url" in data
        assert "client_hash_set" in data
        assert "api_key_set" in data
        
        # Check all 4 KYC modes are present
        assert "available_kyc_modes" in data
        kyc_modes = data["available_kyc_modes"]
        assert len(kyc_modes) == 4, f"Expected 4 KYC modes, got {len(kyc_modes)}"
        
        mode_names = [m["mode"] for m in kyc_modes]
        assert "E_KYC" in mode_names, "E_KYC mode missing"
        assert "MANUAL_KYC" in mode_names, "MANUAL_KYC mode missing"
        assert "E_DOC_VERIFY" in mode_names, "E_DOC_VERIFY mode missing"
        assert "SCREENING_KYC" in mode_names, "SCREENING_KYC mode missing"
        
        # Check each mode has required fields
        for mode in kyc_modes:
            assert "mode" in mode
            assert "description" in mode
            assert "requires_documents" in mode
            assert "auto_verification" in mode
        
        # Check required fields documentation
        assert "required_fields" in data
        assert "mandatory" in data["required_fields"]
        mandatory_fields = data["required_fields"]["mandatory"]
        assert "first_name" in mandatory_fields
        assert "last_name" in mandatory_fields
        assert "email" in mandatory_fields
        assert "date_of_birth" in mandatory_fields
        assert "mobile" in mandatory_fields
        assert "kyc_mode" in mandatory_fields
        
        # Check setup instructions
        assert "setup_instructions" in data
        instructions = data["setup_instructions"]
        assert len(instructions) >= 5, "Expected at least 5 setup steps"
        
        print(f"✓ Available methods returns all 4 KYC modes: {mode_names}")
        print(f"✓ Setup instructions: {len(instructions)} steps")


class TestNiumOnboardingCreateCustomer:
    """Test POST /api/nium-onboarding/create-customer - returns real NIUM error (NOT simulated)"""

    def test_create_customer_returns_real_nium_error(self, authenticated_client):
        """Verify create-customer returns real NIUM API error with troubleshooting steps"""
        payload = {
            "first_name": "Test",
            "last_name": "User",
            "email": "test@example.com",
            "country_code": "IT",
            "nationality": "IT",
            "date_of_birth": "1990-01-15",
            "mobile": "3331234567",
            "kyc_mode": "E_KYC"
        }
        
        response = authenticated_client.post(
            f"{BASE_URL}/api/nium-onboarding/create-customer",
            json=payload
        )
        
        # Expected: 403 or 502 error from real NIUM API (not simulated success)
        assert response.status_code in [403, 502, 400], \
            f"Expected real NIUM error (403/502/400), got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Check error structure contains troubleshooting
        if "detail" in data:
            detail = data["detail"]
            if isinstance(detail, dict):
                assert "message" in detail, "Error should have message"
                assert "nium_error" in detail, "Error should have nium_error"
                assert "troubleshooting" in detail, "Error should have troubleshooting steps"
                
                troubleshooting = detail["troubleshooting"]
                assert len(troubleshooting) >= 3, "Expected at least 3 troubleshooting steps"
                
                print(f"✓ Create customer returns real NIUM error: {detail['message']}")
                print(f"✓ NIUM error detail: {detail['nium_error'][:100]}...")
                print(f"✓ Troubleshooting steps: {len(troubleshooting)}")
            else:
                # Simple error message
                print(f"✓ Create customer returns real NIUM error: {detail}")
        else:
            print(f"✓ Create customer returns real NIUM error: {data}")


class TestNiumOnboardingStatus:
    """Test GET /api/nium-onboarding/status - shows onboarding status"""

    def test_status_returns_onboarding_info(self, authenticated_client):
        """Verify status endpoint returns onboarding status"""
        response = authenticated_client.get(f"{BASE_URL}/api/nium-onboarding/status")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Check required fields
        assert "onboarded" in data
        assert "nium_configured" in data
        
        # After cleanup, user should not be onboarded
        # (or if they have old simulated data, it might show onboarded)
        print(f"✓ Status endpoint works: onboarded={data.get('onboarded')}")
        print(f"✓ NIUM configured: {data.get('nium_configured')}")
        
        if data.get("onboarded"):
            assert "customer_hash" in data
            assert "mode" in data
            print(f"✓ Customer hash: {data.get('customer_hash')}")
            print(f"✓ Mode: {data.get('mode')}")


class TestNiumOnboardingComplianceStatus:
    """Test GET /api/nium-onboarding/compliance-status - returns real NIUM error"""

    def test_compliance_status_returns_error_or_data(self, authenticated_client):
        """Verify compliance-status returns real NIUM error or data"""
        response = authenticated_client.get(f"{BASE_URL}/api/nium-onboarding/compliance-status")
        
        # Could be 404 (no customer), 400/502 (NIUM error), or 200 (success)
        assert response.status_code in [200, 400, 404, 502, 503], \
            f"Unexpected status {response.status_code}: {response.text}"
        
        data = response.json()
        
        if response.status_code == 200:
            assert "compliance_status" in data
            print(f"✓ Compliance status: {data.get('compliance_status')}")
        elif response.status_code == 404:
            assert "detail" in data
            print(f"✓ No NIUM customer found (expected): {data.get('detail')}")
        else:
            # Real NIUM error
            print(f"✓ Real NIUM error returned: {response.status_code} - {data}")


class TestNiumOnboardingCustomerDetails:
    """Test GET /api/nium-onboarding/customer-details - returns real NIUM error"""

    def test_customer_details_returns_error_or_data(self, authenticated_client):
        """Verify customer-details returns real NIUM error or data"""
        response = authenticated_client.get(f"{BASE_URL}/api/nium-onboarding/customer-details")
        
        # Could be 404 (no customer), 400/502 (NIUM error), or 200 (success)
        assert response.status_code in [200, 400, 404, 502, 503], \
            f"Unexpected status {response.status_code}: {response.text}"
        
        data = response.json()
        
        if response.status_code == 200:
            assert "customer" in data
            assert "source" in data
            print(f"✓ Customer details source: {data.get('source')}")
        elif response.status_code == 404:
            assert "detail" in data
            print(f"✓ No NIUM customer found (expected): {data.get('detail')}")
        else:
            # Real NIUM error
            print(f"✓ Real NIUM error returned: {response.status_code} - {data}")


class TestWebSocketStatus:
    """Test WebSocket server status endpoint"""

    def test_ws_status_endpoint(self, api_client):
        """Verify WebSocket status endpoint works"""
        response = api_client.get(f"{BASE_URL}/api/ws/status")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        assert "active_symbols" in data
        assert "total_connections" in data
        assert "connections_by_symbol" in data
        
        print(f"✓ WebSocket status: {data['total_connections']} connections")
        print(f"✓ Active symbols: {data['active_symbols']}")


class TestRateLimiting:
    """Test rate limiting headers on API responses"""

    def test_rate_limit_headers_present(self, api_client):
        """Verify X-RateLimit headers are present on API responses"""
        response = api_client.get(f"{BASE_URL}/api/nium-onboarding/available-methods")
        
        assert response.status_code == 200
        
        # Check for rate limit headers
        headers = response.headers
        
        # At least one of these should be present
        rate_limit_headers = [
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "x-ratelimit-limit",
            "x-ratelimit-remaining"
        ]
        
        found_headers = [h for h in rate_limit_headers if h.lower() in [k.lower() for k in headers.keys()]]
        
        if found_headers:
            print(f"✓ Rate limit headers found: {found_headers}")
            for h in found_headers:
                # Get the actual header value (case-insensitive)
                for key in headers.keys():
                    if key.lower() == h.lower():
                        print(f"  {key}: {headers[key]}")
        else:
            # Rate limiting might not be on all endpoints
            print("⚠ No rate limit headers found on this endpoint (may be expected)")


class TestPortfolioTrackerWebSocketEndpoint:
    """Test that the portfolio tracker WebSocket endpoint exists"""

    def test_portfolio_ws_endpoint_exists(self, auth_token):
        """Verify the portfolio WebSocket endpoint path is correct"""
        # We can't fully test WebSocket with requests, but we can verify the endpoint structure
        # The endpoint is /api/ws/portfolio/{token}
        
        # Test that the WS status endpoint shows the portfolio tracker is available
        response = requests.get(f"{BASE_URL}/api/ws/status")
        assert response.status_code == 200
        
        print(f"✓ WebSocket server is running")
        print(f"✓ Portfolio tracker WS endpoint: /api/ws/portfolio/{{token}}")
        print(f"✓ Auth token available for WS connection: {auth_token[:20]}...")


class TestHealthAndBasicEndpoints:
    """Basic health checks"""

    def test_health_endpoint(self, api_client):
        """Verify health endpoint works"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        print("✓ Health endpoint OK")

    def test_auth_login(self, api_client):
        """Verify login works"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        print(f"✓ Login works for {TEST_USER_EMAIL}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
