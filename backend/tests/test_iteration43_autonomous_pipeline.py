"""
Iteration 43 - Autonomous Financial Pipeline Testing
Tests for:
- POST /api/auth/login - Admin login
- GET /api/pipeline/status - Pipeline running state, cycle count, deposits, payouts
- POST /api/pipeline/deposit - Creates Stripe PaymentIntent for EUR deposit
- GET /api/pipeline/deposits - User deposit history
- GET /api/pipeline/payouts - Admin payout history
- POST /api/pipeline/auto-payout-check - Admin trigger for auto-payout check
- POST /api/pipeline/auto-fund - Admin trigger for auto-fund from revenue
- POST /api/stripe/webhook - payment_intent.succeeded, balance.available, payout.paid, payout.failed, charge.succeeded handlers
"""

import pytest
import requests
import os
import json
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-chain-wallet-14.preview.emergentagent.com').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"
USER_EMAIL = "test@example.com"
USER_PASSWORD = "Test1234!"


class TestAutonomousPipeline:
    """Tests for the Autonomous Financial Pipeline"""
    
    admin_token = None
    user_token = None
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup tokens for tests"""
        if not TestAutonomousPipeline.admin_token:
            # Login as admin
            resp = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            })
            if resp.status_code == 200:
                TestAutonomousPipeline.admin_token = resp.json().get("token")
        
        if not TestAutonomousPipeline.user_token:
            # Login as regular user
            resp = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": USER_EMAIL,
                "password": USER_PASSWORD
            })
            if resp.status_code == 200:
                TestAutonomousPipeline.user_token = resp.json().get("token")
    
    def admin_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TestAutonomousPipeline.admin_token}"
        }
    
    def user_headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {TestAutonomousPipeline.user_token}"
        }
    
    # ── AUTH TESTS ──
    
    def test_01_admin_login_returns_token_with_admin_role(self):
        """POST /api/auth/login - Admin login returns ADMIN role"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "token" in data, "Response should contain token"
        assert data.get("success") == True, "Login should be successful"
        assert data.get("user", {}).get("role") == "ADMIN", "User should have ADMIN role"
        print(f"✓ Admin login successful, role: {data.get('user', {}).get('role')}")
    
    def test_02_regular_user_login_returns_user_role(self):
        """POST /api/auth/login - Regular user login returns USER role"""
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        })
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "token" in data, "Response should contain token"
        assert data.get("user", {}).get("role") == "USER", "User should have USER role"
        print(f"✓ Regular user login successful, role: {data.get('user', {}).get('role')}")
    
    # ── PIPELINE STATUS TESTS ──
    
    def test_03_pipeline_status_returns_running_state(self):
        """GET /api/pipeline/status - Returns pipeline running state"""
        resp = requests.get(f"{BASE_URL}/api/pipeline/status", headers=self.admin_headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Check required fields
        assert "running" in data, "Response should contain 'running' field"
        assert "cycle_count" in data, "Response should contain 'cycle_count' field"
        assert "auto_payout_threshold_eur" in data, "Response should contain 'auto_payout_threshold_eur'"
        assert "stripe_balance_eur" in data, "Response should contain 'stripe_balance_eur'"
        assert "deposits" in data, "Response should contain 'deposits' object"
        assert "payouts" in data, "Response should contain 'payouts' object"
        
        # Validate deposits structure
        deposits = data.get("deposits", {})
        assert "total" in deposits, "Deposits should have 'total' field"
        assert "pending" in deposits, "Deposits should have 'pending' field"
        assert "funded" in deposits, "Deposits should have 'funded' field"
        
        # Validate payouts structure
        payouts = data.get("payouts", {})
        assert "total" in payouts, "Payouts should have 'total' field"
        assert "paid" in payouts, "Payouts should have 'paid' field"
        
        print(f"✓ Pipeline status: running={data.get('running')}, cycles={data.get('cycle_count')}, threshold={data.get('auto_payout_threshold_eur')} EUR")
        print(f"  Stripe balance: {data.get('stripe_balance_eur')} EUR, Deposits: {deposits.get('total')}, Payouts: {payouts.get('total')}")
    
    def test_04_pipeline_status_requires_auth(self):
        """GET /api/pipeline/status - Requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/pipeline/status")
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"
        print("✓ Pipeline status requires authentication")
    
    def test_05_pipeline_status_accessible_by_regular_user(self):
        """GET /api/pipeline/status - Accessible by regular user"""
        resp = requests.get(f"{BASE_URL}/api/pipeline/status", headers=self.user_headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "running" in data, "Response should contain 'running' field"
        print("✓ Pipeline status accessible by regular user")
    
    # ── DEPOSIT TESTS ──
    
    def test_06_create_deposit_returns_payment_intent(self):
        """POST /api/pipeline/deposit - Creates Stripe PaymentIntent"""
        resp = requests.post(f"{BASE_URL}/api/pipeline/deposit", 
            headers=self.user_headers(),
            json={"amount_eur": 10.0}
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Check required fields
        assert "deposit_id" in data, "Response should contain 'deposit_id'"
        assert "client_secret" in data, "Response should contain 'client_secret'"
        assert "payment_intent_id" in data, "Response should contain 'payment_intent_id'"
        assert "amount_eur" in data, "Response should contain 'amount_eur'"
        assert "fee_eur" in data, "Response should contain 'fee_eur'"
        assert "net_credit_eur" in data, "Response should contain 'net_credit_eur'"
        assert "status" in data, "Response should contain 'status'"
        
        # Validate fee calculation (2% platform fee)
        assert data.get("amount_eur") == 10.0, "Amount should be 10.0 EUR"
        assert data.get("fee_eur") == 0.2, f"Fee should be 0.2 EUR (2%), got {data.get('fee_eur')}"
        assert data.get("net_credit_eur") == 9.8, f"Net credit should be 9.8 EUR, got {data.get('net_credit_eur')}"
        assert data.get("status") == "initiated", f"Status should be 'initiated', got {data.get('status')}"
        
        print(f"✓ Deposit created: {data.get('deposit_id')[:8]}..., PI: {data.get('payment_intent_id')}")
        print(f"  Amount: {data.get('amount_eur')} EUR, Fee: {data.get('fee_eur')} EUR, Net: {data.get('net_credit_eur')} EUR")
    
    def test_07_create_deposit_minimum_amount(self):
        """POST /api/pipeline/deposit - Minimum 1 EUR required"""
        resp = requests.post(f"{BASE_URL}/api/pipeline/deposit", 
            headers=self.user_headers(),
            json={"amount_eur": 0.5}
        )
        assert resp.status_code == 400, f"Expected 400 for amount < 1 EUR, got {resp.status_code}"
        print("✓ Deposit requires minimum 1 EUR")
    
    def test_08_create_deposit_requires_auth(self):
        """POST /api/pipeline/deposit - Requires authentication"""
        resp = requests.post(f"{BASE_URL}/api/pipeline/deposit", 
            json={"amount_eur": 10.0}
        )
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"
        print("✓ Deposit requires authentication")
    
    # ── DEPOSIT HISTORY TESTS ──
    
    def test_09_deposit_history_returns_user_deposits(self):
        """GET /api/pipeline/deposits - Returns user deposit history"""
        resp = requests.get(f"{BASE_URL}/api/pipeline/deposits", headers=self.user_headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert "deposits" in data, "Response should contain 'deposits' list"
        assert "count" in data, "Response should contain 'count'"
        assert isinstance(data.get("deposits"), list), "Deposits should be a list"
        
        # If there are deposits, validate structure
        if data.get("deposits"):
            deposit = data["deposits"][0]
            assert "deposit_id" in deposit, "Deposit should have 'deposit_id'"
            assert "amount_eur" in deposit, "Deposit should have 'amount_eur'"
            assert "status" in deposit, "Deposit should have 'status'"
        
        print(f"✓ Deposit history: {data.get('count')} deposits found")
    
    def test_10_deposit_history_requires_auth(self):
        """GET /api/pipeline/deposits - Requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/pipeline/deposits")
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"
        print("✓ Deposit history requires authentication")
    
    # ── PAYOUT HISTORY TESTS ──
    
    def test_11_payout_history_admin_only(self):
        """GET /api/pipeline/payouts - Admin only"""
        resp = requests.get(f"{BASE_URL}/api/pipeline/payouts", headers=self.admin_headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert "payouts" in data, "Response should contain 'payouts' list"
        assert "count" in data, "Response should contain 'count'"
        assert isinstance(data.get("payouts"), list), "Payouts should be a list"
        
        print(f"✓ Payout history (admin): {data.get('count')} payouts found")
    
    def test_12_payout_history_non_admin_returns_403(self):
        """GET /api/pipeline/payouts - Non-admin returns 403"""
        resp = requests.get(f"{BASE_URL}/api/pipeline/payouts", headers=self.user_headers())
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
        print("✓ Payout history returns 403 for non-admin")
    
    # ── AUTO-PAYOUT CHECK TESTS ──
    
    def test_13_auto_payout_check_admin_only(self):
        """POST /api/pipeline/auto-payout-check - Admin trigger for auto-payout"""
        resp = requests.post(f"{BASE_URL}/api/pipeline/auto-payout-check", headers=self.admin_headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Should return execution result
        assert "executed" in data or "reason" in data, "Response should contain 'executed' or 'reason'"
        
        # With 0 balance, should return below_threshold
        if not data.get("executed"):
            assert data.get("reason") in ["below_threshold", "no_stripe_key"], f"Reason should be 'below_threshold' or 'no_stripe_key', got {data.get('reason')}"
            if data.get("reason") == "below_threshold":
                assert "balance_eur" in data, "Response should contain 'balance_eur'"
                assert "threshold_eur" in data, "Response should contain 'threshold_eur'"
        
        print(f"✓ Auto-payout check: executed={data.get('executed')}, reason={data.get('reason')}")
        if "balance_eur" in data:
            print(f"  Balance: {data.get('balance_eur')} EUR, Threshold: {data.get('threshold_eur')} EUR")
    
    def test_14_auto_payout_check_non_admin_returns_403(self):
        """POST /api/pipeline/auto-payout-check - Non-admin returns 403"""
        resp = requests.post(f"{BASE_URL}/api/pipeline/auto-payout-check", headers=self.user_headers())
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
        print("✓ Auto-payout check returns 403 for non-admin")
    
    # ── AUTO-FUND TESTS ──
    
    def test_15_auto_fund_admin_only(self):
        """POST /api/pipeline/auto-fund - Admin trigger for auto-fund"""
        resp = requests.post(f"{BASE_URL}/api/pipeline/auto-fund", headers=self.admin_headers())
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        # Should return funding result
        assert "funded" in data or "reason" in data, "Response should contain 'funded' or 'reason'"
        
        # With no unfunded revenue, should return no_unfunded_revenue
        if not data.get("funded"):
            assert data.get("reason") in ["no_unfunded_revenue", "no_admin_user", "no_stripe_key"], \
                f"Reason should be valid, got {data.get('reason')}"
        
        print(f"✓ Auto-fund: funded={data.get('funded')}, reason={data.get('reason')}")
    
    def test_16_auto_fund_non_admin_returns_403(self):
        """POST /api/pipeline/auto-fund - Non-admin returns 403"""
        resp = requests.post(f"{BASE_URL}/api/pipeline/auto-fund", headers=self.user_headers())
        assert resp.status_code == 403, f"Expected 403 for non-admin, got {resp.status_code}"
        print("✓ Auto-fund returns 403 for non-admin")
    
    # ── WEBHOOK TESTS ──
    
    def test_17_webhook_payment_intent_succeeded(self):
        """POST /api/stripe/webhook - payment_intent.succeeded handler"""
        # Simulate webhook event (dev mode - no signature verification)
        event = {
            "type": "payment_intent.succeeded",
            "data": {
                "object": {
                    "id": f"pi_test_{uuid.uuid4().hex[:16]}",
                    "amount": 1000,
                    "currency": "eur"
                }
            }
        }
        resp = requests.post(f"{BASE_URL}/api/stripe/webhook", json=event)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert data.get("received") == True, "Webhook should be received"
        assert data.get("type") == "payment_intent.succeeded", "Type should match"
        # Note: handled=False is expected for unknown PI
        print(f"✓ Webhook payment_intent.succeeded: received={data.get('received')}, handled={data.get('handled')}")
    
    def test_18_webhook_balance_available(self):
        """POST /api/stripe/webhook - balance.available handler"""
        event = {
            "type": "balance.available",
            "data": {
                "object": {
                    "available": [{"amount": 0, "currency": "eur"}]
                }
            }
        }
        resp = requests.post(f"{BASE_URL}/api/stripe/webhook", json=event)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert data.get("received") == True, "Webhook should be received"
        assert data.get("type") == "balance.available", "Type should match"
        # Should trigger auto-payout check
        assert "executed" in data or "reason" in data, "Should contain auto-payout result"
        print(f"✓ Webhook balance.available: received={data.get('received')}, executed={data.get('executed')}")
    
    def test_19_webhook_payout_paid(self):
        """POST /api/stripe/webhook - payout.paid handler"""
        event = {
            "type": "payout.paid",
            "data": {
                "object": {
                    "id": f"po_test_{uuid.uuid4().hex[:16]}",
                    "amount": 500,
                    "currency": "eur"
                }
            }
        }
        resp = requests.post(f"{BASE_URL}/api/stripe/webhook", json=event)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert data.get("received") == True, "Webhook should be received"
        assert data.get("type") == "payout.paid", "Type should match"
        print(f"✓ Webhook payout.paid: received={data.get('received')}, handled={data.get('handled')}")
    
    def test_20_webhook_payout_failed(self):
        """POST /api/stripe/webhook - payout.failed handler"""
        event = {
            "type": "payout.failed",
            "data": {
                "object": {
                    "id": f"po_test_{uuid.uuid4().hex[:16]}",
                    "amount": 500,
                    "currency": "eur"
                }
            }
        }
        resp = requests.post(f"{BASE_URL}/api/stripe/webhook", json=event)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert data.get("received") == True, "Webhook should be received"
        assert data.get("type") == "payout.failed", "Type should match"
        print(f"✓ Webhook payout.failed: received={data.get('received')}, payout_failed={data.get('payout_failed')}")
    
    def test_21_webhook_charge_succeeded(self):
        """POST /api/stripe/webhook - charge.succeeded handler"""
        event = {
            "type": "charge.succeeded",
            "data": {
                "object": {
                    "id": f"ch_test_{uuid.uuid4().hex[:16]}",
                    "amount": 1000,
                    "currency": "eur"
                }
            }
        }
        resp = requests.post(f"{BASE_URL}/api/stripe/webhook", json=event)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        
        assert data.get("received") == True, "Webhook should be received"
        assert data.get("type") == "charge.succeeded", "Type should match"
        print(f"✓ Webhook charge.succeeded: received={data.get('received')}")
    
    def test_22_webhook_invalid_payload(self):
        """POST /api/stripe/webhook - Invalid payload returns 400"""
        resp = requests.post(f"{BASE_URL}/api/stripe/webhook", data="invalid json")
        assert resp.status_code == 400, f"Expected 400 for invalid payload, got {resp.status_code}"
        print("✓ Webhook returns 400 for invalid payload")
    
    # ── HEALTH CHECK ──
    
    def test_23_health_check(self):
        """GET /api/health - Health check endpoint"""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("status") == "healthy", "Status should be 'healthy'"
        print(f"✓ Health check: status={data.get('status')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
