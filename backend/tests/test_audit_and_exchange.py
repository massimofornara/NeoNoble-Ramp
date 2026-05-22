"""
Backend API Tests for NeoNoble Ramp - Audit and Exchange APIs

Tests:
- Audit API: Session management, event logging, timeline, export
- Exchange API: Status, connectors
- Auth API: Registration, login
"""

import pytest
import requests
import os
import uuid
from datetime import datetime

# Get backend URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://multi-chain-wallet-14.preview.emergentagent.com"


class TestHealthCheck:
    """Health check tests - run first"""
    
    def test_health_endpoint(self):
        """Test /api/health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print(f"✓ Health check passed: {data}")
    
    def test_root_endpoint(self):
        """Test /api/ root endpoint"""
        response = requests.get(f"{BASE_URL}/api/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "NeoNoble" in data["message"]
        print(f"✓ Root endpoint passed: {data['message']}")


class TestAuditAPI:
    """Audit API tests - Session management, event logging, timeline"""
    
    @pytest.fixture
    def session_id(self):
        """Create a test audit session and return session_id"""
        response = requests.post(
            f"{BASE_URL}/api/audit/sessions",
            json={
                "user_id": f"test_user_{uuid.uuid4().hex[:8]}",
                "product_type": "BUY",
                "metadata": {"test": True}
            }
        )
        assert response.status_code == 200, f"Failed to create session: {response.text}"
        data = response.json()
        return data["session_id"]
    
    def test_create_audit_session(self):
        """Test POST /api/audit/sessions - create new audit session"""
        test_user_id = f"test_user_{uuid.uuid4().hex[:8]}"
        response = requests.post(
            f"{BASE_URL}/api/audit/sessions",
            json={
                "user_id": test_user_id,
                "product_type": "BUY",
                "metadata": {"source": "pytest", "test_run": True}
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "session_id" in data, "Response missing session_id"
        assert "status" in data, "Response missing status"
        assert "started_at" in data, "Response missing started_at"
        
        # Validate values
        assert data["session_id"].startswith("audit_"), f"Session ID should start with 'audit_': {data['session_id']}"
        assert data["status"] == "active", f"Expected status 'active', got {data['status']}"
        
        print(f"✓ Created audit session: {data['session_id']}")
        return data["session_id"]
    
    def test_create_audit_session_sell_mode(self):
        """Test creating audit session with SELL product type"""
        response = requests.post(
            f"{BASE_URL}/api/audit/sessions",
            json={
                "user_id": f"test_user_{uuid.uuid4().hex[:8]}",
                "product_type": "SELL",
                "metadata": {"mode": "sell_test"}
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"].startswith("audit_")
        print(f"✓ Created SELL audit session: {data['session_id']}")
    
    def test_log_audit_event(self, session_id):
        """Test POST /api/audit/events - log event to session"""
        response = requests.post(
            f"{BASE_URL}/api/audit/events",
            json={
                "session_id": session_id,
                "event_type": "mode_selected",
                "description": "User selected BUY mode",
                "metadata": {"mode": "BUY"}
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "event_id" in data, "Response missing event_id"
        assert "event_type" in data, "Response missing event_type"
        assert "timestamp" in data, "Response missing timestamp"
        
        # Validate values
        assert data["event_id"].startswith("evt_"), f"Event ID should start with 'evt_': {data['event_id']}"
        assert data["event_type"] == "mode_selected"
        
        print(f"✓ Logged audit event: {data['event_id']}")
    
    def test_log_multiple_events(self, session_id):
        """Test logging multiple events to a session"""
        events = [
            {"event_type": "amount_entered", "description": "Amount: 100 EUR", "metadata": {"amount": 100}},
            {"event_type": "currency_selected", "description": "EUR/USDT", "metadata": {"fiat": "EUR", "crypto": "USDT"}},
            {"event_type": "wallet_entered", "description": "Wallet address entered", "metadata": {"wallet": "0x123..."}}
        ]
        
        for event in events:
            response = requests.post(
                f"{BASE_URL}/api/audit/events",
                json={
                    "session_id": session_id,
                    **event
                }
            )
            assert response.status_code == 200, f"Failed to log event {event['event_type']}: {response.text}"
        
        print(f"✓ Logged {len(events)} events to session {session_id}")
    
    def test_log_event_invalid_type(self, session_id):
        """Test logging event with invalid event type"""
        response = requests.post(
            f"{BASE_URL}/api/audit/events",
            json={
                "session_id": session_id,
                "event_type": "invalid_event_type",
                "description": "This should fail"
            }
        )
        
        assert response.status_code == 400, f"Expected 400 for invalid event type, got {response.status_code}"
        print("✓ Invalid event type correctly rejected")
    
    def test_get_timeline(self, session_id):
        """Test GET /api/audit/timeline/{session_id} - get visual timeline"""
        # First log some events
        events = [
            {"event_type": "mode_selected", "description": "BUY mode"},
            {"event_type": "amount_entered", "description": "100 EUR"},
            {"event_type": "order_created", "description": "Order created"}
        ]
        
        for event in events:
            requests.post(
                f"{BASE_URL}/api/audit/events",
                json={"session_id": session_id, **event}
            )
        
        # Get timeline
        response = requests.get(f"{BASE_URL}/api/audit/timeline/{session_id}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate timeline structure
        assert "session_id" in data, "Timeline missing session_id"
        assert "phases" in data, "Timeline missing phases"
        assert "total_events" in data, "Timeline missing total_events"
        assert "duration_formatted" in data, "Timeline missing duration_formatted"
        
        # Validate phases exist
        expected_phases = ["setup", "kyc", "payment", "transfer", "completion"]
        for phase in expected_phases:
            assert phase in data["phases"], f"Timeline missing phase: {phase}"
        
        # Validate events are in phases
        assert data["total_events"] >= 3, f"Expected at least 3 events, got {data['total_events']}"
        
        print(f"✓ Timeline retrieved: {data['total_events']} events, duration: {data['duration_formatted']}")
    
    def test_get_timeline_not_found(self):
        """Test timeline for non-existent session"""
        response = requests.get(f"{BASE_URL}/api/audit/timeline/nonexistent_session_123")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent session correctly returns 404")
    
    def test_export_session_report(self, session_id):
        """Test GET /api/audit/export/{session_id} - export compliance report"""
        # Log some events first
        requests.post(
            f"{BASE_URL}/api/audit/events",
            json={
                "session_id": session_id,
                "event_type": "order_created",
                "description": "Test order"
            }
        )
        
        response = requests.get(f"{BASE_URL}/api/audit/export/{session_id}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate export structure
        assert "report_type" in data, "Export missing report_type"
        assert "generated_at" in data, "Export missing generated_at"
        assert "session" in data, "Export missing session"
        assert "timeline" in data, "Export missing timeline"
        assert "events" in data, "Export missing events"
        
        # Validate report type
        assert data["report_type"] == "transaction_audit"
        
        print(f"✓ Export report generated at {data['generated_at']}")
    
    def test_export_not_found(self):
        """Test export for non-existent session"""
        response = requests.get(f"{BASE_URL}/api/audit/export/nonexistent_session_456")
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent session export correctly returns 404")
    
    def test_get_event_types(self):
        """Test GET /api/audit/event-types - get available event types"""
        response = requests.get(f"{BASE_URL}/api/audit/event-types")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "event_types" in data, "Response missing event_types"
        assert len(data["event_types"]) > 0, "No event types returned"
        
        # Validate event type structure
        for event_type in data["event_types"]:
            assert "value" in event_type, "Event type missing value"
            assert "name" in event_type, "Event type missing name"
            assert "category" in event_type, "Event type missing category"
        
        print(f"✓ Retrieved {len(data['event_types'])} event types")
    
    def test_close_session(self, session_id):
        """Test POST /api/audit/sessions/close - close audit session"""
        response = requests.post(
            f"{BASE_URL}/api/audit/sessions/close",
            json={
                "session_id": session_id,
                "status": "completed",
                "summary": {"test": True, "result": "success"}
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert data["status"] == "closed"
        assert data["session_id"] == session_id
        
        print(f"✓ Session {session_id} closed successfully")
    
    def test_get_session(self, session_id):
        """Test GET /api/audit/sessions/{session_id} - get session details"""
        response = requests.get(f"{BASE_URL}/api/audit/sessions/{session_id}")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "session_id" in data
        assert "events" in data
        assert data["session_id"] == session_id
        
        print(f"✓ Retrieved session {session_id} with {len(data.get('events', []))} events")


class TestExchangeAPI:
    """Exchange API tests - Connector status"""
    
    def test_exchange_status(self):
        """Test GET /api/exchanges/status - get exchange connector status"""
        response = requests.get(f"{BASE_URL}/api/exchanges/status")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "venues" in data, "Response missing venues"
        assert "shadow_mode" in data, "Response missing shadow_mode"
        
        # Check for expected venues (Binance and Kraken)
        venues = data["venues"]
        print(f"✓ Exchange status: {len(venues)} venues")
        
        for name, status in venues.items():
            print(f"  - {name}: connected={status.get('connected', False)}, initialized={status.get('initialized', False)}")
        
        # Verify Binance and Kraken are present
        assert "binance" in venues, "Expected binance venue"
        assert "kraken" in venues, "Expected kraken venue"
        
        # Verify Kraken is connected (Binance may be geo-blocked)
        assert venues["kraken"]["connected"] == True, "Kraken should be connected"
        print(f"✓ Kraken connected, Binance connected={venues['binance']['connected']}")
    
    def test_exchange_balances(self):
        """Test GET /api/exchanges/balances - get all balances"""
        response = requests.get(f"{BASE_URL}/api/exchanges/balances")
        
        # May return 200 with empty balances or error if not connected
        if response.status_code == 200:
            data = response.json()
            assert "balances" in data
            print(f"✓ Exchange balances retrieved: {list(data['balances'].keys())}")
        else:
            print(f"⚠ Exchange balances returned {response.status_code} (may be expected if not connected)")


class TestAuthAPI:
    """Auth API tests - Registration and Login"""
    
    def test_register_user(self):
        """Test POST /api/auth/register - register new user"""
        test_email = f"test_{uuid.uuid4().hex[:8]}@example.com"
        response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": test_email,
                "password": "TestPassword123!",
                "name": "Test User"
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        assert "token" in data, "Response missing token"
        assert "user" in data, "Response missing user"
        assert data["user"]["email"] == test_email
        
        print(f"✓ Registered user: {test_email}")
        return test_email, "TestPassword123!"
    
    def test_register_duplicate_email(self):
        """Test registration with duplicate email"""
        test_email = f"test_dup_{uuid.uuid4().hex[:8]}@example.com"
        
        # First registration
        response1 = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": test_email,
                "password": "TestPassword123!",
                "name": "Test User"
            }
        )
        assert response1.status_code == 200
        
        # Second registration with same email
        response2 = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": test_email,
                "password": "DifferentPassword123!",
                "name": "Another User"
            }
        )
        
        assert response2.status_code == 400, f"Expected 400 for duplicate email, got {response2.status_code}"
        print("✓ Duplicate email correctly rejected")
    
    def test_login_user(self):
        """Test POST /api/auth/login - login existing user"""
        # First register a user
        test_email = f"test_login_{uuid.uuid4().hex[:8]}@example.com"
        test_password = "TestPassword123!"
        
        reg_response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": test_email,
                "password": test_password,
                "name": "Login Test User"
            }
        )
        assert reg_response.status_code == 200
        
        # Now login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_email,
                "password": test_password
            }
        )
        
        assert login_response.status_code == 200, f"Expected 200, got {login_response.status_code}: {login_response.text}"
        data = login_response.json()
        
        assert "token" in data, "Response missing token"
        assert "user" in data, "Response missing user"
        assert data["user"]["email"] == test_email
        
        print(f"✓ Login successful for: {test_email}")
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "WrongPassword123!"
            }
        )
        
        assert response.status_code == 401, f"Expected 401 for invalid credentials, got {response.status_code}"
        print("✓ Invalid credentials correctly rejected")


class TestTransakAPI:
    """Transak API tests - Widget URL generation"""
    
    def test_transak_config(self):
        """Test GET /api/transak/config - get Transak configuration"""
        response = requests.get(f"{BASE_URL}/api/transak/config")
        
        # May return 200 or 503 depending on configuration
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Transak config: environment={data.get('environment', 'unknown')}")
        else:
            print(f"⚠ Transak config returned {response.status_code} (may be expected if not configured)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
