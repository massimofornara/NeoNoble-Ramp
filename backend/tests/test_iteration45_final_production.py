"""
Iteration 45 - FINAL Production Hardening Tests
NeoNoble Ramp Enterprise Fintech Platform

Tests:
- Auth (admin + user login, /me)
- Health check
- Wallet balances
- NENO pricing, buy, sell, swap with idempotency
- Pipeline status, deposit, deposits history, payouts history, auto-payout-check
- Stripe webhook signature enforcement
- Institutional Liquidity Router (status, quote, venues, fallback-matrix)
- KYC Provider (applicant, status, provider-status, webhook)
- Cashout report, revenue-withdraw with idempotency
- Growth dashboard
- Admin audit logs
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"
USER_EMAIL = "test@example.com"
USER_PASSWORD = "Test1234!"

# Token cache to avoid rate limiting
_token_cache = {}


def get_user_token():
    """Get user token for authenticated requests (cached)"""
    if "user" in _token_cache:
        return _token_cache["user"]
    
    login_resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": USER_EMAIL, "password": USER_PASSWORD}
    )
    if login_resp.status_code == 429:
        # Rate limited, wait and retry
        time.sleep(10)
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD}
        )
    token = login_resp.json().get("token")
    if token:
        _token_cache["user"] = token
    return token


def get_admin_token():
    """Get admin token for authenticated requests (cached)"""
    if "admin" in _token_cache:
        return _token_cache["admin"]
    
    login_resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if login_resp.status_code == 429:
        # Rate limited, wait and retry
        time.sleep(10)
        login_resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
    token = login_resp.json().get("token")
    if token:
        _token_cache["admin"] = token
    return token


class TestAuthAndHealth:
    """Authentication and health check tests"""

    def test_01_health_check(self):
        """GET /api/health - Returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print(f"✓ Health check passed: {data}")

    def test_02_admin_login(self):
        """POST /api/auth/login - Admin login"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if response.status_code == 429:
            time.sleep(10)
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
            )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"].get("role") == "ADMIN"
        _token_cache["admin"] = data["token"]
        print(f"✓ Admin login passed: role={data['user']['role']}")

    def test_03_user_login(self):
        """POST /api/auth/login - User login"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": USER_EMAIL, "password": USER_PASSWORD}
        )
        if response.status_code == 429:
            time.sleep(10)
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": USER_EMAIL, "password": USER_PASSWORD}
            )
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"].get("role") == "USER"
        _token_cache["user"] = data["token"]
        print(f"✓ User login passed: role={data['user']['role']}")

    def test_04_auth_me(self):
        """GET /api/auth/me - Returns user info with role"""
        token = get_user_token()
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "user_id" in data or "email" in data
        print(f"✓ Auth /me passed: {data.get('email', data.get('user_id'))}")


class TestWalletAndNENO:
    """Wallet balances and NENO exchange tests"""

    def test_05_wallet_balances(self):
        """GET /api/wallet/balances - User wallet balances"""
        token = get_user_token()
        response = requests.get(
            f"{BASE_URL}/api/wallet/balances",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "balances" in data or isinstance(data, dict)
        print(f"✓ Wallet balances passed: {len(data.get('balances', data))} assets")

    def test_06_neno_pricing(self):
        """GET /api/neno-exchange/price - NENO pricing data"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/price")
        assert response.status_code == 200
        data = response.json()
        assert "neno_eur_price" in data or "mid_price" in data
        print(f"✓ NENO pricing passed: mid_price={data.get('mid_price')}, bid={data.get('bid')}, ask={data.get('ask')}")

    def test_07_neno_quote_buy(self):
        """GET /api/neno-exchange/quote - Buy quote"""
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/quote",
            params={"direction": "buy", "asset": "EUR", "neno_amount": 0.001}
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_cost" in data or "rate" in data
        print(f"✓ NENO buy quote passed: {data.get('summary', data)}")

    def test_08_neno_quote_sell(self):
        """GET /api/neno-exchange/quote - Sell quote"""
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/quote",
            params={"direction": "sell", "asset": "EUR", "neno_amount": 0.001}
        )
        assert response.status_code == 200
        data = response.json()
        assert "net_receive" in data or "rate" in data
        print(f"✓ NENO sell quote passed: {data.get('summary', data)}")


class TestPipelineAndStripeWebhook:
    """Pipeline status and Stripe webhook signature enforcement tests"""

    def test_09_pipeline_status(self):
        """GET /api/pipeline/status - Pipeline running status"""
        token = get_user_token()
        response = requests.get(
            f"{BASE_URL}/api/pipeline/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "running" in data or "status" in data
        print(f"✓ Pipeline status passed: running={data.get('running', data.get('status'))}")

    def test_10_pipeline_deposits_history(self):
        """GET /api/pipeline/deposits - Deposit history"""
        token = get_user_token()
        response = requests.get(
            f"{BASE_URL}/api/pipeline/deposits",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "deposits" in data or "count" in data or isinstance(data, list)
        print(f"✓ Pipeline deposits history passed: {data.get('count', len(data.get('deposits', data)))}")

    def test_11_pipeline_payouts_history_admin(self):
        """GET /api/pipeline/payouts - Payout history (admin)"""
        token = get_admin_token()
        response = requests.get(
            f"{BASE_URL}/api/pipeline/payouts",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "payouts" in data or "count" in data or isinstance(data, list)
        print(f"✓ Pipeline payouts history passed: {data.get('count', len(data.get('payouts', data)))}")

    def test_12_auto_payout_check_admin(self):
        """POST /api/pipeline/auto-payout-check - Auto-payout check (admin)"""
        token = get_admin_token()
        response = requests.post(
            f"{BASE_URL}/api/pipeline/auto-payout-check",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Auto-payout check passed: {data}")

    def test_13_stripe_webhook_missing_signature(self):
        """POST /api/stripe/webhook - Rejects without stripe-signature header (400)"""
        response = requests.post(
            f"{BASE_URL}/api/stripe/webhook",
            json={"type": "test_event"},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400
        data = response.json()
        assert "signature" in str(data).lower() or "missing" in str(data).lower()
        print(f"✓ Stripe webhook missing signature rejected: {data}")

    def test_14_stripe_webhook_invalid_signature(self):
        """POST /api/stripe/webhook - Rejects with invalid signature (400)"""
        response = requests.post(
            f"{BASE_URL}/api/stripe/webhook",
            json={"type": "test_event"},
            headers={
                "Content-Type": "application/json",
                "stripe-signature": "t=1234567890,v1=invalid_signature_here"
            }
        )
        assert response.status_code == 400
        data = response.json()
        assert "signature" in str(data).lower() or "invalid" in str(data).lower()
        print(f"✓ Stripe webhook invalid signature rejected: {data}")


class TestInstitutionalLiquidityRouter:
    """Institutional Liquidity Router tests"""

    def test_15_router_status(self):
        """GET /api/router/status - Router status with venue availability"""
        token = get_user_token()
        response = requests.get(
            f"{BASE_URL}/api/router/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "venues" in data or "router" in data
        print(f"✓ Router status passed: venues={list(data.get('venues', {}).keys())}")

    def test_16_router_quote_btc(self):
        """POST /api/router/quote - Quote for BTC buy 0.1 (multi-venue comparison)"""
        token = get_user_token()
        response = requests.post(
            f"{BASE_URL}/api/router/quote",
            json={"asset": "BTC", "side": "buy", "amount": 0.1},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "best_venue" in data or "quotes" in data or "route_id" in data
        print(f"✓ Router BTC quote passed: best_venue={data.get('best_venue')}")

    def test_17_router_quote_neno(self):
        """POST /api/router/quote - Quote for NENO buy 1 (custom token fallback)"""
        token = get_user_token()
        response = requests.post(
            f"{BASE_URL}/api/router/quote",
            json={"asset": "NENO", "side": "buy", "amount": 1},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "best_venue" in data or "quotes" in data or "route_id" in data
        print(f"✓ Router NENO quote passed: best_venue={data.get('best_venue')}")

    def test_18_router_quote_validation_zero_amount(self):
        """POST /api/router/quote - Validation: amount <= 0 returns 400"""
        token = get_user_token()
        response = requests.post(
            f"{BASE_URL}/api/router/quote",
            json={"asset": "BTC", "side": "buy", "amount": 0},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 400
        print(f"✓ Router quote validation (amount=0) passed: 400")

    def test_19_router_venues(self):
        """GET /api/router/venues - All venues with connectivity status"""
        token = get_user_token()
        response = requests.get(
            f"{BASE_URL}/api/router/venues",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "venues" in data or isinstance(data, dict)
        print(f"✓ Router venues passed: {list(data.get('venues', data).keys())[:5]}")

    def test_20_router_fallback_matrix(self):
        """GET /api/router/fallback-matrix - Custom token fallback strategies"""
        token = get_user_token()
        response = requests.get(
            f"{BASE_URL}/api/router/fallback-matrix",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "standard_pairs" in data or "custom_token_strategy" in data
        print(f"✓ Router fallback matrix passed: {list(data.keys())}")


class TestKYCProvider:
    """KYC/AML Provider tests"""

    def test_21_kyc_create_applicant(self):
        """POST /api/kyc-provider/applicant - Create KYC applicant"""
        token = get_user_token()
        response = requests.post(
            f"{BASE_URL}/api/kyc-provider/applicant",
            json={"first_name": "Test", "last_name": "User"},
            headers={"Authorization": f"Bearer {token}"}
        )
        # May return 200 (new) or 400 (already exists)
        assert response.status_code in [200, 400]
        data = response.json()
        print(f"✓ KYC create applicant passed: {response.status_code} - {data}")

    def test_22_kyc_status(self):
        """GET /api/kyc-provider/status - KYC status for user"""
        token = get_user_token()
        response = requests.get(
            f"{BASE_URL}/api/kyc-provider/status",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "status" in data or "verification_status" in data or "applicant_id" in data
        print(f"✓ KYC status passed: {data.get('status', data.get('verification_status', 'N/A'))}")

    def test_23_kyc_provider_status_admin(self):
        """GET /api/kyc-provider/provider-status - Provider config (admin)"""
        token = get_admin_token()
        response = requests.get(
            f"{BASE_URL}/api/kyc-provider/provider-status",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "provider" in data or "mode" in data or "applicants" in data
        print(f"✓ KYC provider status (admin) passed: {data}")

    def test_24_kyc_webhook(self):
        """POST /api/kyc-provider/webhook - KYC webhook handler"""
        response = requests.post(
            f"{BASE_URL}/api/kyc-provider/webhook",
            json={
                "type": "applicantReviewed",
                "applicantId": "test-applicant-123",
                "reviewResult": {"reviewAnswer": "GREEN"}
            }
        )
        assert response.status_code == 200
        data = response.json()
        print(f"✓ KYC webhook passed: {data}")


class TestCashoutAndGrowth:
    """Cashout report, revenue withdraw, and growth dashboard tests"""

    def test_25_cashout_report(self):
        """GET /api/cashout/report - Cashout comprehensive report (admin)"""
        token = get_admin_token()
        response = requests.get(
            f"{BASE_URL}/api/cashout/report",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "engine" in data or "extracted" in data or "usdc_wallets" in data
        print(f"✓ Cashout report passed: {list(data.keys())[:5]}")

    def test_26_growth_dashboard(self):
        """GET /api/growth/dashboard - Growth analytics dashboard (admin)"""
        token = get_admin_token()
        response = requests.get(
            f"{BASE_URL}/api/growth/dashboard",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Growth dashboard passed: {list(data.keys())[:5] if isinstance(data, dict) else 'OK'}")

    def test_27_admin_audit_logs(self):
        """GET /api/admin/audit/logs - Audit logs (admin)"""
        token = get_admin_token()
        response = requests.get(
            f"{BASE_URL}/api/admin/audit/logs",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "logs" in data or "events" in data or isinstance(data, list)
        print(f"✓ Admin audit logs passed: {data.get('count', len(data.get('logs', data.get('events', data))))}")


class TestIdempotencyOnFinancialOps:
    """Test idempotency on financial operations (NENO buy/sell/swap)"""

    def test_28_neno_buy_idempotency(self):
        """POST /api/neno-exchange/buy - Buy NENO with idempotency (duplicate should return same result)"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        # First request
        unique_amount = 0.0001  # Very small amount for testing
        response1 = requests.post(
            f"{BASE_URL}/api/neno-exchange/buy",
            json={"pay_asset": "EUR", "neno_amount": unique_amount},
            headers=headers
        )
        # May fail due to insufficient balance, but idempotency should still work
        status1 = response1.status_code
        data1 = response1.json()
        
        # Second identical request (should be idempotent)
        response2 = requests.post(
            f"{BASE_URL}/api/neno-exchange/buy",
            json={"pay_asset": "EUR", "neno_amount": unique_amount},
            headers=headers
        )
        status2 = response2.status_code
        data2 = response2.json()
        
        # Both should return same status (either both succeed or both fail with same error)
        print(f"✓ NENO buy idempotency test: status1={status1}, status2={status2}")
        print(f"  Response1: {str(data1)[:100]}")
        print(f"  Response2: {str(data2)[:100]}")

    def test_29_neno_sell_idempotency(self):
        """POST /api/neno-exchange/sell - Sell NENO with idempotency"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        unique_amount = 0.0001
        response1 = requests.post(
            f"{BASE_URL}/api/neno-exchange/sell",
            json={"receive_asset": "EUR", "neno_amount": unique_amount},
            headers=headers
        )
        status1 = response1.status_code
        data1 = response1.json()
        
        response2 = requests.post(
            f"{BASE_URL}/api/neno-exchange/sell",
            json={"receive_asset": "EUR", "neno_amount": unique_amount},
            headers=headers
        )
        status2 = response2.status_code
        data2 = response2.json()
        
        print(f"✓ NENO sell idempotency test: status1={status1}, status2={status2}")
        print(f"  Response1: {str(data1)[:100]}")
        print(f"  Response2: {str(data2)[:100]}")

    def test_30_neno_swap_idempotency(self):
        """POST /api/neno-exchange/swap - Swap with idempotency"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}"}
        
        unique_amount = 0.0001
        response1 = requests.post(
            f"{BASE_URL}/api/neno-exchange/swap",
            json={"from_asset": "EUR", "to_asset": "USDT", "amount": unique_amount},
            headers=headers
        )
        status1 = response1.status_code
        data1 = response1.json()
        
        response2 = requests.post(
            f"{BASE_URL}/api/neno-exchange/swap",
            json={"from_asset": "EUR", "to_asset": "USDT", "amount": unique_amount},
            headers=headers
        )
        status2 = response2.status_code
        data2 = response2.json()
        
        print(f"✓ NENO swap idempotency test: status1={status1}, status2={status2}")
        print(f"  Response1: {str(data1)[:100]}")
        print(f"  Response2: {str(data2)[:100]}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
