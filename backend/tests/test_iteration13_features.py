"""
Iteration 13 Backend Tests - New Features:
- Admin Audit Log Viewer (/api/admin/audit/*)
- Export CSV endpoints (/api/export/*)
- NIUM Customer Onboarding (/api/nium-onboarding/*)
- Rate Limiting Middleware (X-RateLimit-* headers)
- NENO Exchange /market endpoint (bugfix)
- Microservices Architecture Plan (/api/monitoring/architecture)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"
USER_EMAIL = "testchart@example.com"
USER_PASSWORD = "Test1234!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip(f"Admin login failed: {resp.status_code} {resp.text}")


@pytest.fixture(scope="module")
def user_token():
    """Get regular user authentication token."""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": USER_EMAIL,
        "password": USER_PASSWORD
    })
    if resp.status_code == 200:
        return resp.json().get("token")
    pytest.skip(f"User login failed: {resp.status_code} {resp.text}")


def admin_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def user_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ============ ADMIN AUDIT LOG TESTS ============

class TestAdminAuditStats:
    """Test GET /api/admin/audit/stats - Admin audit statistics."""

    def test_audit_stats_requires_admin(self, user_token):
        """Regular user should be denied access to audit stats."""
        resp = requests.get(f"{BASE_URL}/api/admin/audit/stats", headers=user_headers(user_token))
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
        print("PASS: Non-admin user correctly denied access to audit stats")

    def test_audit_stats_admin_access(self, admin_token):
        """Admin should get audit statistics."""
        resp = requests.get(f"{BASE_URL}/api/admin/audit/stats", headers=admin_headers(admin_token))
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Verify expected fields
        assert "total_users" in data
        assert "total_neno_transactions" in data
        assert "total_banking_transactions" in data
        assert "kyc_pending" in data
        assert "kyc_approved" in data
        assert "aml_alerts" in data
        assert "active_margin_positions" in data
        print(f"PASS: Admin audit stats returned: {data}")


class TestAdminAuditLogs:
    """Test GET /api/admin/audit/logs - Admin audit log viewer."""

    def test_audit_logs_requires_admin(self, user_token):
        """Regular user should be denied access to audit logs."""
        resp = requests.get(f"{BASE_URL}/api/admin/audit/logs?page=1&page_size=10", headers=user_headers(user_token))
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
        print("PASS: Non-admin user correctly denied access to audit logs")

    def test_audit_logs_admin_access(self, admin_token):
        """Admin should get paginated audit logs."""
        resp = requests.get(f"{BASE_URL}/api/admin/audit/logs?page=1&page_size=10", headers=admin_headers(admin_token))
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "logs" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert isinstance(data["logs"], list)
        print(f"PASS: Admin audit logs returned {len(data['logs'])} logs, total: {data['total']}")


class TestAdminAuditExportCSV:
    """Test GET /api/admin/audit/export/csv - CSV export of audit logs."""

    def test_audit_export_requires_admin(self, user_token):
        """Regular user should be denied access to audit export."""
        resp = requests.get(f"{BASE_URL}/api/admin/audit/export/csv?days=30", headers=user_headers(user_token))
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
        print("PASS: Non-admin user correctly denied access to audit export")

    def test_audit_export_csv_admin(self, admin_token):
        """Admin should be able to export audit logs as CSV."""
        resp = requests.get(f"{BASE_URL}/api/admin/audit/export/csv?days=30", headers=admin_headers(admin_token))
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert "text/csv" in resp.headers.get("Content-Type", "")
        assert "attachment" in resp.headers.get("Content-Disposition", "")
        # Verify CSV has header row
        content = resp.text
        assert "timestamp" in content.lower() or "source" in content.lower()
        print(f"PASS: Admin audit CSV export successful, {len(content)} bytes")


# ============ USER EXPORT CSV TESTS ============

class TestExportTradesCSV:
    """Test GET /api/export/trades/csv - Export user trades as CSV."""

    def test_export_trades_requires_auth(self):
        """Unauthenticated request should fail."""
        resp = requests.get(f"{BASE_URL}/api/export/trades/csv")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        print("PASS: Unauthenticated export trades request denied")

    def test_export_trades_csv(self, user_token):
        """Authenticated user should get trades CSV."""
        resp = requests.get(f"{BASE_URL}/api/export/trades/csv", headers=user_headers(user_token))
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert "text/csv" in resp.headers.get("Content-Type", "")
        content = resp.text
        # Verify CSV header
        assert "Data" in content or "Tipo" in content or "Asset" in content
        print(f"PASS: User trades CSV export successful, {len(content)} bytes")


class TestExportPortfolioCSV:
    """Test GET /api/export/portfolio/csv - Export user portfolio as CSV."""

    def test_export_portfolio_csv(self, user_token):
        """Authenticated user should get portfolio CSV."""
        resp = requests.get(f"{BASE_URL}/api/export/portfolio/csv", headers=user_headers(user_token))
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert "text/csv" in resp.headers.get("Content-Type", "")
        content = resp.text
        # Verify CSV header
        assert "Asset" in content or "Saldo" in content
        print(f"PASS: User portfolio CSV export successful, {len(content)} bytes")


class TestExportMarginCSV:
    """Test GET /api/export/margin/csv - Export user margin positions as CSV."""

    def test_export_margin_csv(self, user_token):
        """Authenticated user should get margin positions CSV."""
        resp = requests.get(f"{BASE_URL}/api/export/margin/csv", headers=user_headers(user_token))
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        assert "text/csv" in resp.headers.get("Content-Type", "")
        content = resp.text
        # Verify CSV header
        assert "Data Apertura" in content or "Coppia" in content or "Direzione" in content
        print(f"PASS: User margin CSV export successful, {len(content)} bytes")


# ============ NIUM ONBOARDING TESTS ============

class TestNiumOnboardingStatus:
    """Test GET /api/nium-onboarding/status - NIUM onboarding status."""

    def test_nium_status_requires_auth(self):
        """Unauthenticated request should fail."""
        resp = requests.get(f"{BASE_URL}/api/nium-onboarding/status")
        assert resp.status_code in [401, 403], f"Expected 401/403, got {resp.status_code}"
        print("PASS: Unauthenticated NIUM status request denied")

    def test_nium_status(self, user_token):
        """Authenticated user should get NIUM onboarding status."""
        resp = requests.get(f"{BASE_URL}/api/nium-onboarding/status", headers=user_headers(user_token))
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "onboarded" in data
        print(f"PASS: NIUM onboarding status: {data}")


class TestNiumCreateCustomer:
    """Test POST /api/nium-onboarding/create-customer - Auto NIUM customer creation."""

    def test_nium_create_customer(self, user_token):
        """Create NIUM customer (simulated fallback expected)."""
        resp = requests.post(f"{BASE_URL}/api/nium-onboarding/create-customer", 
            headers=user_headers(user_token),
            json={
                "first_name": "Test",
                "last_name": "User",
                "email": USER_EMAIL,
                "country_code": "IT",
                "nationality": "IT"
            })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "customer_hash" in data
        assert "status" in data
        # Expect simulated or existing status
        assert data["status"] in ["simulated", "simulated_fallback", "simulated_error", "existing", "live"]
        print(f"PASS: NIUM customer creation: {data['status']}, hash: {data['customer_hash'][:20]}...")


# ============ NENO EXCHANGE TESTS ============

class TestNenoExchangeMarket:
    """Test GET /api/neno-exchange/market - Dynamic NENO market info (bugfix verified)."""

    def test_neno_market_info(self):
        """Get NENO market info with all conversion rates."""
        resp = requests.get(f"{BASE_URL}/api/neno-exchange/market")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "neno_eur_price" in data
        assert "neno_usd_price" in data
        assert "fee_percent" in data
        assert "supported_assets" in data
        assert "pairs" in data
        # Verify pairs structure
        assert isinstance(data["pairs"], dict)
        assert len(data["pairs"]) > 0
        print(f"PASS: NENO market info - EUR price: {data['neno_eur_price']}, pairs: {len(data['pairs'])}")


class TestNenoExchangePrice:
    """Test GET /api/neno-exchange/price - NENO price with rate limit headers."""

    def test_neno_price_with_rate_limit_headers(self):
        """Get NENO price and verify rate limit headers are present."""
        resp = requests.get(f"{BASE_URL}/api/neno-exchange/price")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "neno_eur_price" in data
        assert "base_price" in data
        assert "pricing_model" in data
        # Verify rate limit headers
        assert "X-RateLimit-Remaining" in resp.headers, "Missing X-RateLimit-Remaining header"
        assert "X-RateLimit-Limit" in resp.headers, "Missing X-RateLimit-Limit header"
        print(f"PASS: NENO price: {data['neno_eur_price']}, Rate-Limit-Remaining: {resp.headers.get('X-RateLimit-Remaining')}")


# ============ RATE LIMITING TESTS ============

class TestRateLimitMiddleware:
    """Test rate limiting middleware - X-RateLimit-* headers."""

    def test_rate_limit_headers_on_api_calls(self, user_token):
        """Verify rate limit headers are present on authenticated API calls."""
        resp = requests.get(f"{BASE_URL}/api/wallet/balances", headers=user_headers(user_token))
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
        assert "X-RateLimit-Remaining" in resp.headers, "Missing X-RateLimit-Remaining header"
        assert "X-RateLimit-Limit" in resp.headers, "Missing X-RateLimit-Limit header"
        remaining = int(resp.headers.get("X-RateLimit-Remaining", 0))
        limit = int(resp.headers.get("X-RateLimit-Limit", 0))
        assert limit > 0, "Rate limit should be > 0"
        assert remaining >= 0, "Remaining should be >= 0"
        print(f"PASS: Rate limit headers present - Limit: {limit}, Remaining: {remaining}")


# ============ MICROSERVICES ARCHITECTURE TESTS ============

class TestMonitoringArchitecture:
    """Test GET /api/monitoring/architecture - Microservices architecture plan."""

    def test_architecture_plan(self):
        """Get microservices architecture decomposition plan."""
        resp = requests.get(f"{BASE_URL}/api/monitoring/architecture")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "plan" in data
        assert "domains" in data
        assert "current" in data
        assert data["current"] == "monolith"
        # Verify plan structure
        plan = data["plan"]
        assert "current_state" in plan
        assert "target_state" in plan
        assert "domains" in plan
        assert "migration_steps" in plan
        # Verify domains
        domains = data["domains"]
        assert "core" in domains
        assert "exchange" in domains
        assert "wallet" in domains
        assert "compliance" in domains
        print(f"PASS: Architecture plan returned with {len(domains)} domains")


# ============ WEBSOCKET ORDERBOOK TEST (basic connectivity) ============

class TestWebSocketOrderbook:
    """Test WebSocket /api/ws/orderbook/neno - NENO real-time order book (basic check)."""

    def test_ws_status_endpoint(self):
        """Check WebSocket status endpoint."""
        resp = requests.get(f"{BASE_URL}/api/ws/status")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "active_symbols" in data
        assert "total_connections" in data
        print(f"PASS: WebSocket status - connections: {data['total_connections']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
