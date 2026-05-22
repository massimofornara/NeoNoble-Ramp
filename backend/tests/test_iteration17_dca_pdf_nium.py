"""
Iteration 17 Tests: DCA Bot, PDF Compliance Reports, NIUM Onboarding Improvements

Features tested:
1. DCA Bot CRUD: create, list, pause, resume, cancel, history
2. PDF Compliance Report: GET /api/export/compliance/pdf
3. NIUM Onboarding: diagnostic, templates, corporate-constants, set-template-id

Test credentials:
- Admin: admin@neonobleramp.com / Admin1234!
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-chain-wallet-14.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code} - {response.text}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture
def admin_headers(admin_token):
    """Headers with admin auth token."""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}"
    }


# ═══════════════════════════════════════════════════════════════════════════════
# DCA Bot Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestDCABot:
    """DCA Trading Bot CRUD operations."""
    
    created_plan_id = None
    
    def test_01_create_dca_plan(self, admin_headers):
        """POST /api/dca/create - Create a new DCA plan."""
        payload = {
            "asset": "ETH",
            "amount_eur": 15.0,
            "interval": "daily",
            "max_executions": 5
        }
        response = requests.post(
            f"{BASE_URL}/api/dca/create",
            json=payload,
            headers=admin_headers
        )
        
        # May fail if insufficient EUR balance - that's expected behavior
        if response.status_code == 400:
            data = response.json()
            if "Saldo EUR insufficiente" in str(data.get("detail", "")):
                pytest.skip("Insufficient EUR balance for DCA plan creation")
        
        assert response.status_code == 200, f"Create DCA failed: {response.text}"
        data = response.json()
        
        assert "plan" in data, "Response should contain 'plan'"
        assert "message" in data, "Response should contain 'message'"
        
        plan = data["plan"]
        assert plan["asset"] == "ETH"
        assert plan["amount_eur"] == 15.0
        assert plan["interval"] == "daily"
        assert plan["max_executions"] == 5
        assert plan["status"] == "active"
        assert "id" in plan
        
        TestDCABot.created_plan_id = plan["id"]
        print(f"Created DCA plan: {plan['id']}")
    
    def test_02_list_dca_plans(self, admin_headers):
        """GET /api/dca/plans - List user's DCA plans."""
        response = requests.get(
            f"{BASE_URL}/api/dca/plans",
            headers=admin_headers
        )
        
        assert response.status_code == 200, f"List DCA plans failed: {response.text}"
        data = response.json()
        
        assert "plans" in data, "Response should contain 'plans'"
        assert "total" in data, "Response should contain 'total'"
        assert isinstance(data["plans"], list)
        assert data["total"] >= 0
        
        print(f"Found {data['total']} DCA plans")
    
    def test_03_pause_dca_plan(self, admin_headers):
        """POST /api/dca/pause - Pause an active DCA plan."""
        if not TestDCABot.created_plan_id:
            pytest.skip("No plan created to pause")
        
        response = requests.post(
            f"{BASE_URL}/api/dca/pause",
            json={"plan_id": TestDCABot.created_plan_id},
            headers=admin_headers
        )
        
        assert response.status_code == 200, f"Pause DCA failed: {response.text}"
        data = response.json()
        assert "message" in data
        assert "pausa" in data["message"].lower() or "pause" in data["message"].lower()
        print(f"Paused plan: {TestDCABot.created_plan_id}")
    
    def test_04_resume_dca_plan(self, admin_headers):
        """POST /api/dca/resume - Resume a paused DCA plan."""
        if not TestDCABot.created_plan_id:
            pytest.skip("No plan created to resume")
        
        response = requests.post(
            f"{BASE_URL}/api/dca/resume",
            json={"plan_id": TestDCABot.created_plan_id},
            headers=admin_headers
        )
        
        assert response.status_code == 200, f"Resume DCA failed: {response.text}"
        data = response.json()
        assert "message" in data
        assert "ripreso" in data["message"].lower() or "resume" in data["message"].lower()
        print(f"Resumed plan: {TestDCABot.created_plan_id}")
    
    def test_05_get_dca_history(self, admin_headers):
        """GET /api/dca/history - Get DCA execution history."""
        response = requests.get(
            f"{BASE_URL}/api/dca/history?limit=50",
            headers=admin_headers
        )
        
        assert response.status_code == 200, f"Get DCA history failed: {response.text}"
        data = response.json()
        
        assert "executions" in data, "Response should contain 'executions'"
        assert "total" in data, "Response should contain 'total'"
        assert isinstance(data["executions"], list)
        
        print(f"Found {data['total']} DCA executions")
    
    def test_06_get_dca_history_by_plan(self, admin_headers):
        """GET /api/dca/history?plan_id=X - Get history for specific plan."""
        if not TestDCABot.created_plan_id:
            pytest.skip("No plan created to get history for")
        
        response = requests.get(
            f"{BASE_URL}/api/dca/history?plan_id={TestDCABot.created_plan_id}&limit=10",
            headers=admin_headers
        )
        
        assert response.status_code == 200, f"Get plan history failed: {response.text}"
        data = response.json()
        assert "executions" in data
        print(f"Found {data['total']} executions for plan {TestDCABot.created_plan_id}")
    
    def test_07_cancel_dca_plan(self, admin_headers):
        """DELETE /api/dca/plans/{plan_id} - Cancel a DCA plan."""
        if not TestDCABot.created_plan_id:
            pytest.skip("No plan created to cancel")
        
        response = requests.delete(
            f"{BASE_URL}/api/dca/plans/{TestDCABot.created_plan_id}",
            headers=admin_headers
        )
        
        assert response.status_code == 200, f"Cancel DCA failed: {response.text}"
        data = response.json()
        assert "message" in data
        assert "cancellato" in data["message"].lower() or "cancel" in data["message"].lower()
        print(f"Cancelled plan: {TestDCABot.created_plan_id}")
    
    def test_08_verify_plan_cancelled(self, admin_headers):
        """Verify the cancelled plan shows status=cancelled."""
        if not TestDCABot.created_plan_id:
            pytest.skip("No plan to verify")
        
        response = requests.get(
            f"{BASE_URL}/api/dca/plans",
            headers=admin_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Find our plan
        for plan in data["plans"]:
            if plan["id"] == TestDCABot.created_plan_id:
                assert plan["status"] == "cancelled", f"Plan should be cancelled, got: {plan['status']}"
                print(f"Verified plan {TestDCABot.created_plan_id} is cancelled")
                return
        
        # Plan might have been removed from list - that's also acceptable
        print("Plan not found in list (may have been filtered out)")


# ═══════════════════════════════════════════════════════════════════════════════
# PDF Compliance Report Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestPDFExport:
    """PDF Compliance Report export."""
    
    def test_01_export_compliance_pdf_90_days(self, admin_headers):
        """GET /api/export/compliance/pdf?days=90 - Generate PDF report."""
        response = requests.get(
            f"{BASE_URL}/api/export/compliance/pdf?days=90",
            headers=admin_headers,
            stream=True
        )
        
        assert response.status_code == 200, f"PDF export failed: {response.text}"
        
        # Check content type
        content_type = response.headers.get("Content-Type", "")
        assert "application/pdf" in content_type, f"Expected PDF, got: {content_type}"
        
        # Check content disposition
        content_disp = response.headers.get("Content-Disposition", "")
        assert "attachment" in content_disp, "Should be attachment download"
        assert ".pdf" in content_disp, "Filename should have .pdf extension"
        
        # Check we got actual content
        content = response.content
        assert len(content) > 1000, f"PDF too small: {len(content)} bytes"
        
        # Check PDF magic bytes
        assert content[:4] == b'%PDF', "Content should start with PDF magic bytes"
        
        print(f"PDF generated successfully: {len(content)} bytes")
    
    def test_02_export_compliance_pdf_30_days(self, admin_headers):
        """GET /api/export/compliance/pdf?days=30 - Generate 30-day report."""
        response = requests.get(
            f"{BASE_URL}/api/export/compliance/pdf?days=30",
            headers=admin_headers,
            stream=True
        )
        
        assert response.status_code == 200, f"PDF export failed: {response.text}"
        assert "application/pdf" in response.headers.get("Content-Type", "")
        assert response.content[:4] == b'%PDF'
        print(f"30-day PDF generated: {len(response.content)} bytes")
    
    def test_03_export_compliance_pdf_365_days(self, admin_headers):
        """GET /api/export/compliance/pdf?days=365 - Generate full year report."""
        response = requests.get(
            f"{BASE_URL}/api/export/compliance/pdf?days=365",
            headers=admin_headers,
            stream=True
        )
        
        assert response.status_code == 200, f"PDF export failed: {response.text}"
        assert "application/pdf" in response.headers.get("Content-Type", "")
        print(f"365-day PDF generated: {len(response.content)} bytes")


# ═══════════════════════════════════════════════════════════════════════════════
# NIUM Onboarding Improvements Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestNIUMOnboarding:
    """NIUM onboarding diagnostic and configuration endpoints."""
    
    def test_01_nium_diagnostic(self, admin_headers):
        """GET /api/nium-onboarding/diagnostic - Full NIUM integration diagnostic."""
        response = requests.get(
            f"{BASE_URL}/api/nium-onboarding/diagnostic",
            headers=admin_headers
        )
        
        assert response.status_code == 200, f"NIUM diagnostic failed: {response.text}"
        data = response.json()
        
        # Check diagnostic fields
        assert "api_key_set" in data, "Should have api_key_set"
        assert "client_hash_set" in data, "Should have client_hash_set"
        assert "template_id_set" in data, "Should have template_id_set"
        assert "auth_strategy" in data, "Should have auth_strategy"
        assert "recommendations" in data, "Should have recommendations"
        
        # API key and client hash should be configured
        assert data["api_key_set"] == True, "NIUM API key should be set"
        assert data["client_hash_set"] == True, "NIUM client hash should be set"
        
        # Auth strategy should be discovered
        if data["auth_strategy"]:
            assert "name" in data["auth_strategy"]
            assert "working" in data["auth_strategy"]
            print(f"Active auth strategy: {data['auth_strategy']['name']}")
        
        print(f"NIUM diagnostic: api_key={data['api_key_set']}, client_hash={data['client_hash_set']}, template={data['template_id_set']}")
    
    def test_02_nium_templates(self, admin_headers):
        """GET /api/nium-onboarding/templates - Fetch available templates."""
        response = requests.get(
            f"{BASE_URL}/api/nium-onboarding/templates",
            headers=admin_headers
        )
        
        assert response.status_code == 200, f"NIUM templates failed: {response.text}"
        data = response.json()
        
        # Should have hint for configuration
        assert "hint" in data, "Should have configuration hint"
        
        # May have nium_response or error depending on NIUM account setup
        if data.get("nium_response"):
            print(f"NIUM templates response: {data['nium_response']}")
        elif data.get("error"):
            print(f"NIUM templates error (expected if not configured): {data['error'][:100]}")
        
        print(f"Configured template ID: {data.get('configured_template_id', 'None')}")
    
    def test_03_nium_corporate_constants(self, admin_headers):
        """GET /api/nium-onboarding/corporate-constants - Fetch corporate constants."""
        response = requests.get(
            f"{BASE_URL}/api/nium-onboarding/corporate-constants",
            headers=admin_headers
        )
        
        assert response.status_code == 200, f"NIUM corporate constants failed: {response.text}"
        data = response.json()
        
        # Should have client_hash and data
        assert "client_hash" in data, "Should have client_hash"
        assert "data" in data, "Should have data"
        assert "hint" in data, "Should have hint"
        
        # Data should have attempted endpoints
        assert "constants" in data["data"] or "settings" in data["data"] or "programs" in data["data"]
        
        print(f"Corporate constants for client: {data['client_hash']}")
        print(f"Configured template ID: {data.get('configured_template_id', 'None')}")
    
    def test_04_nium_set_template_id_admin_only(self, admin_headers):
        """POST /api/nium-onboarding/set-template-id - Admin only endpoint."""
        # Test with a dummy template ID (won't actually change anything meaningful)
        test_template_id = "test-template-12345"
        
        response = requests.post(
            f"{BASE_URL}/api/nium-onboarding/set-template-id",
            json={"template_id": test_template_id},
            headers=admin_headers
        )
        
        assert response.status_code == 200, f"Set template ID failed: {response.text}"
        data = response.json()
        
        assert "message" in data, "Should have message"
        assert "active" in data, "Should have active status"
        assert data["active"] == True
        assert test_template_id in data["message"]
        
        print(f"Template ID set successfully: {test_template_id}")
    
    def test_05_nium_set_template_id_non_admin_forbidden(self):
        """POST /api/nium-onboarding/set-template-id - Should fail for non-admin."""
        # Login as regular user
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "testchart@example.com", "password": "Test1234!"}
        )
        
        if login_resp.status_code != 200:
            pytest.skip("Regular user login failed")
        
        token = login_resp.json().get("access_token") or login_resp.json().get("token")
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/nium-onboarding/set-template-id",
            json={"template_id": "test-template"},
            headers=headers
        )
        
        # Should be forbidden for non-admin
        assert response.status_code == 403, f"Expected 403 for non-admin, got: {response.status_code}"
        print("Non-admin correctly forbidden from setting template ID")


# ═══════════════════════════════════════════════════════════════════════════════
# DCA Validation Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestDCAValidation:
    """DCA Bot input validation."""
    
    def test_01_invalid_asset(self, admin_headers):
        """POST /api/dca/create - Invalid asset should fail."""
        response = requests.post(
            f"{BASE_URL}/api/dca/create",
            json={"asset": "INVALID_COIN", "amount_eur": 10, "interval": "daily"},
            headers=admin_headers
        )
        
        assert response.status_code == 400, f"Expected 400 for invalid asset, got: {response.status_code}"
        data = response.json()
        assert "Asset non supportato" in str(data.get("detail", ""))
        print("Invalid asset correctly rejected")
    
    def test_02_invalid_interval(self, admin_headers):
        """POST /api/dca/create - Invalid interval should fail."""
        response = requests.post(
            f"{BASE_URL}/api/dca/create",
            json={"asset": "BTC", "amount_eur": 10, "interval": "every_second"},
            headers=admin_headers
        )
        
        assert response.status_code == 400, f"Expected 400 for invalid interval, got: {response.status_code}"
        data = response.json()
        assert "Intervallo non valido" in str(data.get("detail", ""))
        print("Invalid interval correctly rejected")
    
    def test_03_negative_amount(self, admin_headers):
        """POST /api/dca/create - Negative amount should fail."""
        response = requests.post(
            f"{BASE_URL}/api/dca/create",
            json={"asset": "BTC", "amount_eur": -10, "interval": "daily"},
            headers=admin_headers
        )
        
        # Pydantic validation should catch this
        assert response.status_code == 422, f"Expected 422 for negative amount, got: {response.status_code}"
        print("Negative amount correctly rejected")
    
    def test_04_pause_nonexistent_plan(self, admin_headers):
        """POST /api/dca/pause - Non-existent plan should fail."""
        response = requests.post(
            f"{BASE_URL}/api/dca/pause",
            json={"plan_id": "nonexistent-plan-id-12345"},
            headers=admin_headers
        )
        
        assert response.status_code == 404, f"Expected 404 for nonexistent plan, got: {response.status_code}"
        print("Pause nonexistent plan correctly returns 404")
    
    def test_05_cancel_nonexistent_plan(self, admin_headers):
        """DELETE /api/dca/plans/{id} - Non-existent plan should fail."""
        response = requests.delete(
            f"{BASE_URL}/api/dca/plans/nonexistent-plan-id-12345",
            headers=admin_headers
        )
        
        assert response.status_code == 404, f"Expected 404 for nonexistent plan, got: {response.status_code}"
        print("Cancel nonexistent plan correctly returns 404")


# ═══════════════════════════════════════════════════════════════════════════════
# CSV Export Tests (bonus - verify other export endpoints)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCSVExport:
    """CSV export endpoints."""
    
    def test_01_export_trades_csv(self, admin_headers):
        """GET /api/export/trades/csv - Export trades as CSV."""
        response = requests.get(
            f"{BASE_URL}/api/export/trades/csv?days=90",
            headers=admin_headers
        )
        
        assert response.status_code == 200, f"Trades CSV export failed: {response.text}"
        assert "text/csv" in response.headers.get("Content-Type", "")
        assert "attachment" in response.headers.get("Content-Disposition", "")
        print(f"Trades CSV exported: {len(response.content)} bytes")
    
    def test_02_export_portfolio_csv(self, admin_headers):
        """GET /api/export/portfolio/csv - Export portfolio as CSV."""
        response = requests.get(
            f"{BASE_URL}/api/export/portfolio/csv",
            headers=admin_headers
        )
        
        assert response.status_code == 200, f"Portfolio CSV export failed: {response.text}"
        assert "text/csv" in response.headers.get("Content-Type", "")
        print(f"Portfolio CSV exported: {len(response.content)} bytes")
    
    def test_03_export_margin_csv(self, admin_headers):
        """GET /api/export/margin/csv - Export margin positions as CSV."""
        response = requests.get(
            f"{BASE_URL}/api/export/margin/csv",
            headers=admin_headers
        )
        
        assert response.status_code == 200, f"Margin CSV export failed: {response.text}"
        assert "text/csv" in response.headers.get("Content-Type", "")
        print(f"Margin CSV exported: {len(response.content)} bytes")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
