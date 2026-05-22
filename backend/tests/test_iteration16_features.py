"""
Iteration 16 Backend Tests - NIUM Multi-Strategy Auth Discovery + Background Scheduler

Tests:
1. NIUM Auth Discovery Status - GET /api/nium-onboarding/auth-discovery-status
2. NIUM Auth Discovery Reset - POST /api/nium-onboarding/auth-discovery-reset
3. NIUM Create Customer (multi-version retry) - POST /api/nium-onboarding/create-customer
4. NIUM Available Methods - GET /api/nium-onboarding/available-methods
5. NIUM Status - GET /api/nium-onboarding/status
6. Price Alerts CRUD - POST/GET /api/alerts/*
7. Alert Check (background task) - POST /api/alerts/check
8. Browser Push Pending - GET /api/browser-push/pending
9. WebSocket Portfolio Status - GET /api/ws/status
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_USER_EMAIL = "testchart@example.com"
TEST_USER_PASSWORD = "Test1234!"
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"


def get_auth_token(email, password):
    """Get authentication token."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": email,
        "password": password
    })
    if response.status_code == 200:
        data = response.json()
        # API returns 'token' not 'access_token'
        return data.get("token") or data.get("access_token")
    return None


class TestNiumAuthDiscovery:
    """NIUM Multi-Strategy Auth Discovery Tests"""

    def test_auth_discovery_status(self):
        """GET /api/nium-onboarding/auth-discovery-status - shows active strategy and all tested strategies"""
        response = requests.get(f"{BASE_URL}/api/nium-onboarding/auth-discovery-status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "active_strategy" in data, "Missing active_strategy field"
        assert "all_strategies" in data, "Missing all_strategies field"
        assert "last_discovery" in data, "Missing last_discovery field"
        assert "discovery_in_progress" in data, "Missing discovery_in_progress field"
        
        # Verify all_strategies is a list with 6 strategies (3 base URLs x 2 auth types)
        assert isinstance(data["all_strategies"], list), "all_strategies should be a list"
        assert len(data["all_strategies"]) == 6, f"Expected 6 strategies, got {len(data['all_strategies'])}"
        
        # Verify each strategy has required fields
        for strategy in data["all_strategies"]:
            assert "name" in strategy, "Strategy missing name"
            assert "base_url" in strategy, "Strategy missing base_url"
            assert "auth_type" in strategy, "Strategy missing auth_type"
            assert "working" in strategy, "Strategy missing working"
        
        # Verify active strategy (should be x-api-key@gateway.nium.com based on logs)
        if data["active_strategy"]:
            assert data["active_strategy"]["working"] == True, "Active strategy should be working"
            print(f"Active strategy: {data['active_strategy']['name']}")
        
        print(f"Auth discovery status: {len(data['all_strategies'])} strategies tested")

    def test_auth_discovery_reset(self):
        """POST /api/nium-onboarding/auth-discovery-reset - force re-discovery"""
        response = requests.post(f"{BASE_URL}/api/nium-onboarding/auth-discovery-reset")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Missing message field"
        assert "all_strategies" in data, "Missing all_strategies field"
        
        # Should have active strategy or message about no working strategy
        if data.get("active"):
            assert data["active"]["working"] == True, "Active strategy should be working"
            print(f"Reset found working strategy: {data['active']['name']}")
        else:
            print(f"Reset message: {data['message']}")

    def test_available_methods_shows_auto_discovery(self):
        """GET /api/nium-onboarding/available-methods - shows auto_discovery enabled"""
        response = requests.get(f"{BASE_URL}/api/nium-onboarding/available-methods")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "nium_configured" in data, "Missing nium_configured field"
        assert "auto_discovery" in data, "Missing auto_discovery field"
        assert data["auto_discovery"] == "enabled", f"Expected auto_discovery=enabled, got {data['auto_discovery']}"
        assert "available_kyc_modes" in data, "Missing available_kyc_modes field"
        assert len(data["available_kyc_modes"]) == 4, f"Expected 4 KYC modes, got {len(data['available_kyc_modes'])}"
        
        print(f"NIUM configured: {data['nium_configured']}, auto_discovery: {data['auto_discovery']}")


class TestNiumOnboarding:
    """NIUM Customer Onboarding Tests"""

    def test_onboarding_status_not_onboarded(self):
        """GET /api/nium-onboarding/status - returns onboarded false with nium_configured true"""
        token = get_auth_token(TEST_USER_EMAIL, TEST_USER_PASSWORD)
        assert token, "Failed to get auth token"
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/nium-onboarding/status", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "onboarded" in data, "Missing onboarded field"
        assert "nium_configured" in data, "Missing nium_configured field"
        assert data["nium_configured"] == True, "NIUM should be configured"
        
        print(f"Onboarding status: onboarded={data['onboarded']}, nium_configured={data['nium_configured']}")

    def test_create_customer_multi_version_retry(self):
        """POST /api/nium-onboarding/create-customer - tries v3,v4,v2,v1 automatically, returns enriched error"""
        token = get_auth_token(TEST_USER_EMAIL, TEST_USER_PASSWORD)
        assert token, "Failed to get auth token"
        
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        # Create customer request with valid data
        payload = {
            "first_name": "Test",
            "last_name": "User",
            "email": f"test_{uuid.uuid4().hex[:8]}@example.com",
            "country_code": "IT",
            "nationality": "IT",
            "date_of_birth": "1990-01-15",
            "mobile": "+393331234567",
            "kyc_mode": "E_KYC",
            "billing_address1": "Via Roma 1",
            "billing_city": "Milano",
            "billing_zip_code": "20100",
            "billing_country": "IT"
        }
        
        response = requests.post(f"{BASE_URL}/api/nium-onboarding/create-customer", json=payload, headers=headers)
        
        # Expected: 404 with templateId error (NIUM Portal configuration needed)
        # The system tries all 4 API versions and returns enriched error
        assert response.status_code in [400, 403, 404, 502], f"Expected error status, got {response.status_code}: {response.text}"
        
        data = response.json()
        detail = data.get("detail", {})
        
        # Verify enriched error response
        if isinstance(detail, dict):
            assert "auto_discovery" in detail or "nium_error" in detail, "Missing enriched error fields"
            if "troubleshooting" in detail:
                assert isinstance(detail["troubleshooting"], list), "troubleshooting should be a list"
                print(f"Troubleshooting steps: {len(detail['troubleshooting'])}")
            print(f"NIUM error (expected): {detail.get('nium_error', str(detail))[:100]}...")
        else:
            print(f"NIUM error (expected): {str(detail)[:100]}...")


class TestPriceAlerts:
    """Price Alerts CRUD Tests"""

    def test_create_price_alert(self):
        """POST /api/alerts/create - create price alert"""
        token = get_auth_token(TEST_USER_EMAIL, TEST_USER_PASSWORD)
        assert token, "Failed to get auth token"
        
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {
            "asset": "BTC",
            "condition": "above",
            "threshold": 65000.0,
            "note": "Test alert from iteration 16"
        }
        
        response = requests.post(f"{BASE_URL}/api/alerts/create", json=payload, headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "alert" in data, "Missing alert field"
        assert data["alert"]["asset"] == "BTC", "Asset mismatch"
        assert data["alert"]["condition"] == "above", "Condition mismatch"
        assert data["alert"]["threshold"] == 65000.0, "Threshold mismatch"
        assert data["alert"]["triggered"] == False, "New alert should not be triggered"
        
        print(f"Created alert: {data['alert']['id']}")

    def test_list_alerts(self):
        """GET /api/alerts - list alerts"""
        token = get_auth_token(TEST_USER_EMAIL, TEST_USER_PASSWORD)
        assert token, "Failed to get auth token"
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/alerts", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "alerts" in data, "Missing alerts field"
        assert "active_count" in data, "Missing active_count field"
        assert isinstance(data["alerts"], list), "alerts should be a list"
        
        print(f"Total alerts: {len(data['alerts'])}, active: {data['active_count']}")

    def test_check_alerts_background_task(self):
        """POST /api/alerts/check - check and trigger alerts (called by background scheduler)"""
        # This endpoint is public (no auth required) for background task usage
        response = requests.post(f"{BASE_URL}/api/alerts/check")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "checked" in data, "Missing checked field"
        assert "triggered" in data, "Missing triggered field"
        
        print(f"Alerts checked: {data['checked']}, triggered: {data['triggered']}")


class TestBrowserPush:
    """Browser Push Notification Tests"""

    def test_get_pending_push_notifications(self):
        """GET /api/browser-push/pending - poll pending push notifications"""
        token = get_auth_token(TEST_USER_EMAIL, TEST_USER_PASSWORD)
        assert token, "Failed to get auth token"
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/api/browser-push/pending", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "notifications" in data, "Missing notifications field"
        assert isinstance(data["notifications"], list), "notifications should be a list"
        
        print(f"Pending push notifications: {len(data['notifications'])}")

    def test_mark_push_delivered(self):
        """POST /api/browser-push/delivered - mark push as delivered"""
        token = get_auth_token(TEST_USER_EMAIL, TEST_USER_PASSWORD)
        assert token, "Failed to get auth token"
        
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.post(f"{BASE_URL}/api/browser-push/delivered", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "marked" in data, "Missing marked field"
        
        print(f"Marked as delivered: {data['marked']}")


class TestWebSocketPortfolio:
    """WebSocket Portfolio Tracker Tests"""

    def test_websocket_status(self):
        """GET /api/ws/status - WebSocket server status"""
        response = requests.get(f"{BASE_URL}/api/ws/status")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # The endpoint returns total_connections and connections_by_symbol
        assert "total_connections" in data, "Missing total_connections field"
        
        print(f"WebSocket status: connections={data['total_connections']}")


class TestBackgroundScheduler:
    """Background Scheduler Verification Tests"""

    def test_scheduler_running_via_logs(self):
        """Verify background scheduler is running by checking health and alert check"""
        # Health check
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Health check failed: {response.status_code}"
        
        # Alert check endpoint works (scheduler calls this every 60s)
        response = requests.post(f"{BASE_URL}/api/alerts/check")
        assert response.status_code == 200, f"Alert check failed: {response.status_code}"
        
        # Auth discovery status (scheduler refreshes every 30min)
        response = requests.get(f"{BASE_URL}/api/nium-onboarding/auth-discovery-status")
        assert response.status_code == 200, f"Auth discovery status failed: {response.status_code}"
        
        data = response.json()
        # If last_discovery is set, scheduler has run at least once
        if data.get("last_discovery"):
            print(f"Scheduler last discovery: {data['last_discovery']}")
        
        print("Background scheduler endpoints verified")


class TestCleanup:
    """Cleanup test data"""

    def test_delete_test_alerts(self):
        """Delete test alerts created during testing"""
        token = get_auth_token(TEST_USER_EMAIL, TEST_USER_PASSWORD)
        if not token:
            print("Skipping cleanup - no auth token")
            return
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Get all alerts
        response = requests.get(f"{BASE_URL}/api/alerts", headers=headers)
        if response.status_code == 200:
            alerts = response.json().get("alerts", [])
            deleted = 0
            for alert in alerts:
                if alert.get("note") == "Test alert from iteration 16":
                    del_response = requests.delete(f"{BASE_URL}/api/alerts/{alert['id']}", headers=headers)
                    if del_response.status_code == 200:
                        deleted += 1
            print(f"Cleaned up {deleted} test alerts")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
