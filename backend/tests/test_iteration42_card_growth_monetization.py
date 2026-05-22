"""
Iteration 42 - Card Issuing Engine, Growth Analytics, Monetization, Incentive Engine Tests

Tests for:
1. Card Issuing Engine (issue, reveal with 2FA, authorize, settlement, monetization)
2. Growth Analytics (dashboard, funnel, retention, ARPU)
3. Monetization Engine (revenue breakdown, daily revenue)
4. Incentive Engine (cashback tiers, rewards, first top-up bonus)
5. Referral viral loop (viral-stats endpoint)
6. Admin-only endpoint protection
"""

import pytest
import requests
import os
import uuid
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-chain-wallet-14.preview.emergentagent.com').rstrip('/')

# Test credentials from test_credentials.md
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"
USER_EMAIL = "test@example.com"
USER_PASSWORD = "Test1234!"

# Token cache to avoid rate limiting
_token_cache = {}


def get_admin_token():
    """Get admin token with caching"""
    if 'admin' in _token_cache:
        return _token_cache['admin']
    
    time.sleep(0.5)  # Small delay to avoid rate limiting
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
    })
    if resp.status_code == 429:
        time.sleep(15)
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL, "password": ADMIN_PASSWORD
        })
    token = resp.json().get("token")
    _token_cache['admin'] = token
    return token


def get_user_token():
    """Get regular user token with caching"""
    if 'user' in _token_cache:
        return _token_cache['user']
    
    time.sleep(0.5)  # Small delay to avoid rate limiting
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": USER_EMAIL, "password": USER_PASSWORD
    })
    if resp.status_code == 429:
        time.sleep(15)
        resp = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER_EMAIL, "password": USER_PASSWORD
        })
    token = resp.json().get("token")
    _token_cache['user'] = token
    return token


class TestAuthAndRoles:
    """Test authentication and role-based access"""
    
    def test_01_admin_login_returns_token_with_admin_role(self):
        """POST /api/auth/login admin@neonobleramp.com / Admin1234! returns token with ADMIN role"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 429:
            time.sleep(15)
            response = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "token" in data, "Response should contain token"
        # Role is in user object
        user_role = data.get("user", {}).get("role")
        assert user_role == "ADMIN", f"Expected ADMIN role, got {user_role}"
        _token_cache['admin'] = data['token']
        print(f"✓ Admin login successful, role: {user_role}")
    
    def test_02_regular_user_login_returns_user_role(self):
        """POST /api/auth/login test@example.com / Test1234! returns token with USER role"""
        time.sleep(1)  # Avoid rate limiting
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": USER_EMAIL,
            "password": USER_PASSWORD
        })
        if response.status_code == 429:
            time.sleep(15)
            response = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": USER_EMAIL,
                "password": USER_PASSWORD
            })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "token" in data, "Response should contain token"
        # Role is in user object
        user_role = data.get("user", {}).get("role")
        assert user_role == "USER", f"Expected USER role, got {user_role}"
        _token_cache['user'] = data['token']
        print(f"✓ Regular user login successful, role: {user_role}")


class TestCardIssuingEngine:
    """Test Card Issuing Engine endpoints"""
    
    def test_03_card_provider_info(self):
        """GET /api/card-engine/provider returns active provider info"""
        response = requests.get(f"{BASE_URL}/api/card-engine/provider")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "active_provider" in data, "Response should contain active_provider"
        assert "available_providers" in data, "Response should contain available_providers"
        assert "features" in data, "Response should contain features"
        print(f"✓ Card provider: {data['active_provider']}, features: {data['features']}")
    
    def test_04_issue_virtual_card(self):
        """POST /api/card-engine/issue creates a new virtual visa card with card_id and status=active"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.post(f"{BASE_URL}/api/card-engine/issue", 
            headers=headers,
            json={"card_type": "virtual", "network": "visa", "currency": "EUR"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "card_id" in data, "Response should contain card_id"
        assert data.get("status") == "active", f"Expected status=active, got {data.get('status')}"
        assert data.get("card_type") == "virtual", f"Expected card_type=virtual, got {data.get('card_type')}"
        assert data.get("network") == "visa", f"Expected network=visa, got {data.get('network')}"
        print(f"✓ Card issued: {data['card_id']}, status: {data['status']}, masked: {data.get('card_number_masked')}")
    
    def test_05_card_reveal_without_2fa_returns_403(self):
        """POST /api/card-engine/reveal without 2FA returns 403 error"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        # First issue a card
        issue_resp = requests.post(f"{BASE_URL}/api/card-engine/issue", 
            headers=headers,
            json={"card_type": "virtual", "network": "visa", "currency": "EUR"}
        )
        card_id = issue_resp.json().get("card_id")
        
        # Try to reveal without OTP
        response = requests.post(f"{BASE_URL}/api/card-engine/reveal",
            headers=headers,
            json={"card_id": card_id}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print(f"✓ Card reveal without 2FA correctly returns 403")
    
    def test_06_card_reveal_with_otp_returns_full_details(self):
        """POST /api/card-engine/reveal with otp_code=123456 returns full PAN, CVV, expiry with 60s countdown"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        # First issue a card
        issue_resp = requests.post(f"{BASE_URL}/api/card-engine/issue", 
            headers=headers,
            json={"card_type": "virtual", "network": "visa", "currency": "EUR"}
        )
        card_id = issue_resp.json().get("card_id")
        
        # Reveal with valid 6-digit OTP
        response = requests.post(f"{BASE_URL}/api/card-engine/reveal",
            headers=headers,
            json={"card_id": card_id, "otp_code": "123456"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "pan" in data, "Response should contain pan"
        assert "cvv" in data, "Response should contain cvv"
        assert "expiry" in data, "Response should contain expiry"
        assert "expires_in_seconds" in data, "Response should contain expires_in_seconds"
        assert data.get("expires_in_seconds") == 60, f"Expected 60s countdown, got {data.get('expires_in_seconds')}"
        print(f"✓ Card revealed: PAN={data['pan'][:4]}****, CVV=***, expiry={data['expiry']}, countdown={data['expires_in_seconds']}s")
    
    def test_07_card_authorize_checks_balance(self):
        """POST /api/card-engine/authorize checks balance and returns authorization_id"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        # First issue a card
        issue_resp = requests.post(f"{BASE_URL}/api/card-engine/issue", 
            headers=headers,
            json={"card_type": "virtual", "network": "visa", "currency": "EUR"}
        )
        card_id = issue_resp.json().get("card_id")
        
        # Try to authorize (will fail due to insufficient balance, but should return proper error)
        response = requests.post(f"{BASE_URL}/api/card-engine/authorize",
            headers=headers,
            json={"card_id": card_id, "merchant": "Test Merchant", "amount": 10.0, "currency": "EUR", "mcc": "5411"}
        )
        # Should return 400 with insufficient_balance reason
        assert response.status_code == 400, f"Expected 400 (insufficient balance), got {response.status_code}: {response.text}"
        assert "insufficient_balance" in response.text.lower() or "autorizzazione rifiutata" in response.text.lower()
        print(f"✓ Card authorization correctly checks balance and returns error for insufficient funds")
    
    def test_08_card_settlement_requires_valid_auth(self):
        """POST /api/card-engine/settlement settles a previously authorized transaction"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        # Try to settle a non-existent authorization
        response = requests.post(f"{BASE_URL}/api/card-engine/settlement",
            headers=headers,
            json={"authorization_id": str(uuid.uuid4())}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}: {response.text}"
        assert "authorization_not_found" in response.text.lower() or "settlement fallito" in response.text.lower()
        print(f"✓ Card settlement correctly validates authorization_id")
    
    def test_09_card_monetization_admin_only(self):
        """GET /api/card-engine/monetization returns card revenue stats (admin only)"""
        token = get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.get(f"{BASE_URL}/api/card-engine/monetization", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "total_cards_active" in data, "Response should contain total_cards_active"
        assert "total_volume" in data, "Response should contain total_volume"
        assert "total_interchange_revenue" in data, "Response should contain total_interchange_revenue"
        assert "total_fx_revenue" in data, "Response should contain total_fx_revenue"
        assert "revenue_streams" in data, "Response should contain revenue_streams"
        print(f"✓ Card monetization stats: cards={data['total_cards_active']}, volume={data['total_volume']}, interchange={data['total_interchange_revenue']}")
    
    def test_10_card_monetization_non_admin_returns_403(self):
        """GET /api/card-engine/monetization with non-admin returns 403"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.get(f"{BASE_URL}/api/card-engine/monetization", headers=headers)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print(f"✓ Card monetization correctly returns 403 for non-admin")


class TestGrowthAnalytics:
    """Test Growth Analytics endpoints"""
    
    def test_11_growth_dashboard_admin_only(self):
        """GET /api/growth/dashboard returns funnel, retention, and ARPU data (admin only)"""
        token = get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.get(f"{BASE_URL}/api/growth/dashboard", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "funnel" in data, "Response should contain funnel"
        assert "retention" in data, "Response should contain retention"
        assert "revenue_per_user" in data, "Response should contain revenue_per_user"
        print(f"✓ Growth dashboard: funnel steps={len(data['funnel'].get('steps', []))}, DAU={data['retention'].get('dau')}, ARPU={data['revenue_per_user'].get('arpu_eur')}")
    
    def test_12_growth_dashboard_non_admin_returns_403(self):
        """GET /api/growth/dashboard with non-admin returns 403"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.get(f"{BASE_URL}/api/growth/dashboard", headers=headers)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print(f"✓ Growth dashboard correctly returns 403 for non-admin")
    
    def test_13_growth_revenue_breakdown(self):
        """GET /api/growth/revenue returns revenue breakdown by source"""
        token = get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.get(f"{BASE_URL}/api/growth/revenue", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "total_revenue_eur" in data, "Response should contain total_revenue_eur"
        assert "trading" in data, "Response should contain trading"
        assert "cards" in data, "Response should contain cards"
        assert "net_revenue_eur" in data, "Response should contain net_revenue_eur"
        print(f"✓ Revenue breakdown: total={data['total_revenue_eur']}, trading={data['trading']}, cards={data['cards']}")
    
    def test_14_growth_revenue_non_admin_returns_403(self):
        """GET /api/growth/revenue with non-admin returns 403"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.get(f"{BASE_URL}/api/growth/revenue", headers=headers)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print(f"✓ Growth revenue correctly returns 403 for non-admin")
    
    def test_15_growth_daily_revenue(self):
        """GET /api/growth/revenue/daily returns 7-day revenue chart data"""
        token = get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.get(f"{BASE_URL}/api/growth/revenue/daily?days=7", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        assert len(data) == 7, f"Expected 7 days of data, got {len(data)}"
        if data:
            assert "date" in data[0], "Each item should contain date"
            assert "revenue" in data[0], "Each item should contain revenue"
            assert "volume" in data[0], "Each item should contain volume"
        print(f"✓ Daily revenue: {len(data)} days of data")


class TestIncentiveEngine:
    """Test Incentive Engine endpoints"""
    
    def test_16_my_tier_returns_cashback_tier(self):
        """GET /api/growth/my-tier returns cashback tier (Base/Silver/Gold/Platinum/Diamond)"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.get(f"{BASE_URL}/api/growth/my-tier", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "current_tier" in data, "Response should contain current_tier"
        assert "cashback_rate" in data, "Response should contain cashback_rate"
        assert "cashback_pct" in data, "Response should contain cashback_pct"
        assert "tiers" in data, "Response should contain tiers"
        valid_tiers = ["Base", "Silver", "Gold", "Platinum", "Diamond"]
        assert data["current_tier"] in valid_tiers, f"Tier should be one of {valid_tiers}, got {data['current_tier']}"
        print(f"✓ User tier: {data['current_tier']}, cashback: {data['cashback_pct']}")
    
    def test_17_my_rewards_returns_summary(self):
        """GET /api/growth/my-rewards returns user reward summary"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.get(f"{BASE_URL}/api/growth/my-rewards", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "tier" in data, "Response should contain tier"
        assert "cashback" in data, "Response should contain cashback"
        assert "referral_earnings" in data, "Response should contain referral_earnings"
        assert "total_rewards_eur" in data, "Response should contain total_rewards_eur"
        print(f"✓ User rewards: tier={data['tier'].get('current_tier')}, cashback={data['cashback']}, total={data['total_rewards_eur']}")
    
    def test_18_claim_topup_bonus(self):
        """POST /api/growth/claim-topup-bonus claims first top-up bonus"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.post(f"{BASE_URL}/api/growth/claim-topup-bonus", headers=headers)
        # May return 200 (eligible) or 400 (already claimed)
        assert response.status_code in [200, 400], f"Expected 200 or 400, got {response.status_code}: {response.text}"
        data = response.json()
        if response.status_code == 200:
            assert "bonus" in data or "eligible" in data, "Response should contain bonus info"
            print(f"✓ First top-up bonus claimed: {data}")
        else:
            print(f"✓ First top-up bonus already claimed (expected behavior)")


class TestReferralViralLoop:
    """Test Referral viral loop endpoints"""
    
    def test_19_viral_stats_returns_network_metrics(self):
        """GET /api/referral/viral-stats returns network volume, viral multiplier, funnel stats"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.get(f"{BASE_URL}/api/referral/viral-stats", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "network_volume_eur" in data, "Response should contain network_volume_eur"
        assert "viral_multiplier" in data, "Response should contain viral_multiplier"
        assert "funnel" in data, "Response should contain funnel"
        assert "total_referrals" in data, "Response should contain total_referrals"
        print(f"✓ Viral stats: network_volume={data['network_volume_eur']}, multiplier={data['viral_multiplier']}, referrals={data['total_referrals']}")
    
    def test_20_referral_code_endpoint(self):
        """GET /api/referral/code returns or creates referral code"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.get(f"{BASE_URL}/api/referral/code", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "code" in data, "Response should contain code"
        assert len(data["code"]) == 8, f"Referral code should be 8 characters, got {len(data['code'])}"
        print(f"✓ Referral code: {data['code']}")
    
    def test_21_referral_stats_endpoint(self):
        """GET /api/referral/stats returns referral statistics"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.get(f"{BASE_URL}/api/referral/stats", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "my_code" in data, "Response should contain my_code"
        assert "total_referrals" in data, "Response should contain total_referrals"
        assert "total_bonus_earned" in data, "Response should contain total_bonus_earned"
        print(f"✓ Referral stats: code={data['my_code']}, referrals={data['total_referrals']}, bonus={data['total_bonus_earned']}")


class TestCashoutRevenueWithdraw:
    """Test Cashout revenue withdrawal endpoints"""
    
    def test_22_revenue_withdraw_admin_only(self):
        """POST /api/cashout/revenue-withdraw works with ADMIN token"""
        token = get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.post(f"{BASE_URL}/api/cashout/revenue-withdraw",
            headers=headers,
            json={"amount": 0.01, "currency": "EUR", "destination_type": "sepa"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "success" in data, "Response should contain success"
        assert "withdrawal" in data, "Response should contain withdrawal"
        print(f"✓ Revenue withdraw successful: {data.get('message')}")
    
    def test_23_revenue_withdraw_non_admin_returns_403(self):
        """POST /api/cashout/revenue-withdraw with non-admin returns 403"""
        token = get_user_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.post(f"{BASE_URL}/api/cashout/revenue-withdraw",
            headers=headers,
            json={"amount": 0.01, "currency": "EUR", "destination_type": "sepa"}
        )
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print(f"✓ Revenue withdraw correctly returns 403 for non-admin")
    
    def test_24_revenue_history_returns_list(self):
        """GET /api/cashout/revenue-history returns withdrawal list"""
        token = get_admin_token()
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        response = requests.get(f"{BASE_URL}/api/cashout/revenue-history", headers=headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "withdrawals" in data, "Response should contain withdrawals"
        assert "count" in data, "Response should contain count"
        print(f"✓ Revenue history: {data['count']} withdrawals")


class TestHealthAndBasics:
    """Basic health checks"""
    
    def test_25_health_check(self):
        """GET /api/health returns healthy status"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data.get("status") == "healthy", f"Expected healthy status, got {data.get('status')}"
        print(f"✓ Health check passed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
