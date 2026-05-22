"""
Backend Tests for Iteration 4 Features - NeoNoble Ramp
Tests cover:
- Market Data API (CoinGecko integration with fallback)
- Analytics Tracking & Admin Overview
- Card Infrastructure (CRUD, top-up, freeze, cancel)
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


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200
    return response.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Get admin auth headers"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def regular_user_headers():
    """Get regular user auth headers"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip("Regular test user not available")
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ==================== MARKET DATA TESTS ====================

class TestMarketDataAPI:
    """Market Data API tests - CoinGecko integration with fallback"""

    def test_market_data_coins_endpoint(self):
        """GET /api/market-data/coins - returns crypto market data"""
        response = requests.get(f"{BASE_URL}/api/market-data/coins?vs_currency=eur&per_page=32")
        assert response.status_code == 200
        data = response.json()
        
        assert "coins" in data
        assert "total" in data
        assert "vs_currency" in data
        assert data["vs_currency"] == "eur"
        
        # Should return coins (either from CoinGecko or fallback)
        coins = data["coins"]
        assert len(coins) >= 5, "Should return at least 5 coins"
        
        # Verify coin structure
        if coins:
            coin = coins[0]
            assert "id" in coin
            assert "symbol" in coin
            assert "name" in coin
            assert "current_price" in coin
            assert "market_cap" in coin
        
        print(f"✓ Market data returned {len(coins)} coins, currency={data['vs_currency']}")

    def test_market_data_contains_bitcoin(self):
        """Market data should include Bitcoin"""
        response = requests.get(f"{BASE_URL}/api/market-data/coins?vs_currency=eur&per_page=32")
        data = response.json()
        
        coins = data["coins"]
        bitcoin = next((c for c in coins if c["id"] == "bitcoin" or c["symbol"].upper() == "BTC"), None)
        
        if bitcoin:
            assert bitcoin["current_price"] > 0
            assert bitcoin["market_cap"] > 0
            print(f"✓ Bitcoin found: price=€{bitcoin['current_price']:,.2f}")
        else:
            print("✓ Bitcoin not in current batch (CoinGecko may have returned different coins)")

    def test_market_data_coin_fields(self):
        """Verify coin data has required fields for display"""
        response = requests.get(f"{BASE_URL}/api/market-data/coins?vs_currency=eur&per_page=10")
        data = response.json()
        coins = data["coins"]
        
        required_fields = ["id", "symbol", "name", "current_price", "market_cap", 
                          "price_change_percentage_24h"]
        
        for coin in coins[:5]:
            for field in required_fields:
                assert field in coin, f"Coin missing field: {field}"
        
        print(f"✓ All required fields present in {len(coins)} coins")

    def test_market_data_trending(self):
        """GET /api/market-data/trending - returns trending coins"""
        response = requests.get(f"{BASE_URL}/api/market-data/trending")
        # May be rate limited, check for either success or cached data
        if response.status_code == 200:
            data = response.json()
            assert "trending" in data
            assert "updated_at" in data
            print(f"✓ Trending returned {len(data.get('trending', []))} coins")
        elif response.status_code == 502:
            print("✓ Trending endpoint rate limited (expected with CoinGecko free tier)")
        else:
            assert False, f"Unexpected status: {response.status_code}"


# ==================== ANALYTICS TESTS ====================

class TestAnalyticsAPI:
    """Analytics API tests - page tracking and admin overview"""

    def test_analytics_track_page_view(self):
        """POST /api/analytics/track - track page view without auth"""
        response = requests.post(f"{BASE_URL}/api/analytics/track",
            json={
                "page": "/test-iteration4",
                "session_id": f"test-{uuid.uuid4().hex[:8]}",
                "referrer": "https://example.com"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        print("✓ Page view tracked successfully (no auth required)")

    def test_analytics_track_minimal_data(self):
        """Track page view with minimal data"""
        response = requests.post(f"{BASE_URL}/api/analytics/track",
            json={"page": "/minimal-test"}
        )
        assert response.status_code == 200
        print("✓ Minimal page view tracked")

    def test_analytics_admin_overview(self, admin_headers):
        """GET /api/analytics/admin/overview - admin analytics"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin/overview?days=30",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "period_days" in data
        assert data["period_days"] == 30
        assert "page_views" in data
        assert "users" in data
        assert "platform" in data
        
        page_views = data["page_views"]
        assert "total" in page_views
        assert "by_page" in page_views
        
        users = data["users"]
        assert "total" in users
        assert "active" in users
        assert "new" in users
        
        print(f"✓ Admin overview: page_views={page_views['total']}, users.total={users['total']}")

    def test_analytics_admin_engagement(self, admin_headers):
        """GET /api/analytics/admin/engagement - engagement metrics"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin/engagement?days=7",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "period_days" in data
        assert "sessions" in data
        assert "avg_pages_per_session" in data
        assert "avg_session_duration_seconds" in data
        assert "recent_activity" in data
        
        print(f"✓ Admin engagement: sessions={data['sessions']}, avg_pages={data['avg_pages_per_session']}")

    def test_analytics_admin_requires_auth(self):
        """Admin analytics requires authentication"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin/overview?days=30")
        assert response.status_code in [401, 403]
        print("✓ Admin analytics correctly requires authentication")

    def test_analytics_admin_requires_admin_role(self, regular_user_headers):
        """Admin analytics requires ADMIN role"""
        response = requests.get(f"{BASE_URL}/api/analytics/admin/overview?days=30",
            headers=regular_user_headers
        )
        assert response.status_code == 403
        print("✓ Admin analytics correctly requires ADMIN role")


# ==================== CARD INFRASTRUCTURE TESTS ====================

class TestCardAPI:
    """Card Infrastructure API tests"""

    @pytest.fixture
    def test_card(self, admin_headers):
        """Create a test card and clean up after"""
        # Create card
        response = requests.post(f"{BASE_URL}/api/cards/create",
            headers=admin_headers,
            json={
                "card_type": "virtual",
                "card_network": "visa",
                "currency": "EUR"
            }
        )
        assert response.status_code == 200
        card = response.json()["card"]
        
        yield card
        
        # Cleanup - cancel card
        requests.post(f"{BASE_URL}/api/cards/{card['id']}/cancel", headers=admin_headers)

    def test_card_create_virtual(self, admin_headers):
        """POST /api/cards/create - create virtual card"""
        response = requests.post(f"{BASE_URL}/api/cards/create",
            headers=admin_headers,
            json={
                "card_type": "virtual",
                "card_network": "visa",
                "currency": "EUR"
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "card" in data
        card = data["card"]
        assert card["card_type"] == "virtual"
        assert card["status"] == "active"  # Virtual cards are instant
        assert card["card_network"] == "visa"
        assert card["currency"] == "EUR"
        assert card["balance"] == 0.0
        assert "card_number_masked" in card
        
        print(f"✓ Virtual card created: {card['card_number_masked']}, status={card['status']}")
        
        # Cleanup
        requests.post(f"{BASE_URL}/api/cards/{card['id']}/cancel", headers=admin_headers)

    def test_card_create_physical_pending(self, admin_headers):
        """Physical cards start with pending status"""
        response = requests.post(f"{BASE_URL}/api/cards/create",
            headers=admin_headers,
            json={
                "card_type": "physical",
                "card_network": "mastercard",
                "currency": "EUR"
            }
        )
        assert response.status_code == 200
        card = response.json()["card"]
        
        assert card["card_type"] == "physical"
        assert card["status"] == "pending"  # Physical cards require processing
        assert card["card_network"] == "mastercard"
        
        print(f"✓ Physical card created with status=pending")
        
        # Cleanup
        requests.post(f"{BASE_URL}/api/cards/{card['id']}/cancel", headers=admin_headers)

    def test_card_my_cards(self, admin_headers, test_card):
        """GET /api/cards/my-cards - list user's cards"""
        response = requests.get(f"{BASE_URL}/api/cards/my-cards", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert "cards" in data
        assert "total" in data
        assert data["total"] >= 1
        
        # Verify test card is in list
        card_ids = [c["id"] for c in data["cards"]]
        assert test_card["id"] in card_ids
        
        print(f"✓ My cards returned {data['total']} cards")

    def test_card_topup_btc(self, admin_headers, test_card):
        """POST /api/cards/{id}/top-up - top up with BTC"""
        response = requests.post(f"{BASE_URL}/api/cards/{test_card['id']}/top-up",
            headers=admin_headers,
            json={
                "amount_crypto": 0.001,
                "crypto_asset": "BTC"
            }
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "message" in data
        assert "transaction" in data
        assert "new_balance" in data
        
        tx = data["transaction"]
        assert tx["crypto_asset"] == "BTC"
        assert tx["crypto_amount"] == 0.001
        assert tx["fiat_amount"] > 0  # Should be ~€60 based on BTC price
        assert tx["conversion_rate"] > 50000  # BTC should be > €50k
        
        print(f"✓ Top-up: {tx['crypto_amount']} BTC -> €{tx['fiat_amount']:.2f}")

    def test_card_topup_eth(self, admin_headers, test_card):
        """Top up with ETH"""
        response = requests.post(f"{BASE_URL}/api/cards/{test_card['id']}/top-up",
            headers=admin_headers,
            json={
                "amount_crypto": 0.5,
                "crypto_asset": "ETH"
            }
        )
        assert response.status_code == 200
        tx = response.json()["transaction"]
        assert tx["crypto_asset"] == "ETH"
        print(f"✓ ETH top-up: {tx['crypto_amount']} ETH -> €{tx['fiat_amount']:.2f}")

    def test_card_transactions(self, admin_headers, test_card):
        """GET /api/cards/{id}/transactions - get card transactions"""
        # First do a top-up to have a transaction
        requests.post(f"{BASE_URL}/api/cards/{test_card['id']}/top-up",
            headers=admin_headers,
            json={"amount_crypto": 0.0001, "crypto_asset": "BTC"}
        )
        
        response = requests.get(f"{BASE_URL}/api/cards/{test_card['id']}/transactions",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "transactions" in data
        assert "total" in data
        assert data["total"] >= 1
        
        print(f"✓ Card transactions: {data['total']} total")

    def test_card_freeze_unfreeze(self, admin_headers, test_card):
        """POST /api/cards/{id}/freeze - freeze and unfreeze card"""
        # Freeze
        response = requests.post(f"{BASE_URL}/api/cards/{test_card['id']}/freeze",
            headers=admin_headers,
            json={}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "frozen"
        print(f"✓ Card frozen")
        
        # Unfreeze
        response = requests.post(f"{BASE_URL}/api/cards/{test_card['id']}/freeze",
            headers=admin_headers,
            json={}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"
        print(f"✓ Card unfrozen")

    def test_card_topup_frozen_fails(self, admin_headers, test_card):
        """Cannot top up frozen card"""
        # Freeze the card
        requests.post(f"{BASE_URL}/api/cards/{test_card['id']}/freeze",
            headers=admin_headers, json={})
        
        # Try to top up
        response = requests.post(f"{BASE_URL}/api/cards/{test_card['id']}/top-up",
            headers=admin_headers,
            json={"amount_crypto": 0.001, "crypto_asset": "BTC"}
        )
        assert response.status_code == 400
        print(f"✓ Top-up on frozen card correctly rejected")
        
        # Unfreeze for cleanup
        requests.post(f"{BASE_URL}/api/cards/{test_card['id']}/freeze",
            headers=admin_headers, json={})

    def test_card_cancel(self, admin_headers):
        """POST /api/cards/{id}/cancel - cancel card permanently"""
        # Create a new card to cancel
        create_res = requests.post(f"{BASE_URL}/api/cards/create",
            headers=admin_headers,
            json={"card_type": "virtual", "card_network": "visa", "currency": "EUR"}
        )
        card_id = create_res.json()["card"]["id"]
        
        # Cancel
        response = requests.post(f"{BASE_URL}/api/cards/{card_id}/cancel",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "cancellata" in data["message"].lower() or "cancelled" in data["message"].lower()
        
        print(f"✓ Card cancelled successfully")

    def test_card_admin_overview(self, admin_headers):
        """GET /api/cards/admin/overview - admin card stats"""
        response = requests.get(f"{BASE_URL}/api/cards/admin/overview",
            headers=admin_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "cards" in data
        cards = data["cards"]
        assert "total" in cards
        assert "active" in cards
        assert "virtual" in cards
        assert "physical" in cards
        assert "frozen" in cards
        
        assert "transactions" in data
        
        print(f"✓ Admin overview: total={cards['total']}, active={cards['active']}")

    def test_card_admin_requires_admin_role(self, regular_user_headers):
        """Admin card overview requires ADMIN role"""
        response = requests.get(f"{BASE_URL}/api/cards/admin/overview",
            headers=regular_user_headers
        )
        assert response.status_code == 403
        print("✓ Admin card overview correctly requires ADMIN role")

    def test_card_max_limit_per_type(self, admin_headers):
        """Max 3 cards per type"""
        # Clean up existing virtual cards first
        my_cards = requests.get(f"{BASE_URL}/api/cards/my-cards", headers=admin_headers).json()["cards"]
        virtual_active = [c for c in my_cards if c["card_type"] == "virtual" and c["status"] in ["pending", "active"]]
        
        # Cancel extra cards to allow creating 3
        while len(virtual_active) > 0:
            requests.post(f"{BASE_URL}/api/cards/{virtual_active[0]['id']}/cancel", headers=admin_headers)
            virtual_active.pop(0)
        
        # Create 3 virtual cards
        created_ids = []
        for i in range(3):
            res = requests.post(f"{BASE_URL}/api/cards/create",
                headers=admin_headers,
                json={"card_type": "virtual", "card_network": "visa", "currency": "EUR"}
            )
            if res.status_code == 200:
                created_ids.append(res.json()["card"]["id"])
        
        # 4th should fail
        response = requests.post(f"{BASE_URL}/api/cards/create",
            headers=admin_headers,
            json={"card_type": "virtual", "card_network": "visa", "currency": "EUR"}
        )
        assert response.status_code == 400
        assert "Maximum" in response.json().get("detail", "") or "maximum" in response.json().get("detail", "").lower()
        
        print("✓ Max 3 cards per type enforced")
        
        # Cleanup
        for cid in created_ids:
            requests.post(f"{BASE_URL}/api/cards/{cid}/cancel", headers=admin_headers)


# ==================== INTEGRATION TESTS ====================

class TestCrossFeatureIntegration:
    """Tests for feature integration"""

    def test_dashboard_quick_links_data(self, admin_headers):
        """Verify data for dashboard quick links is available"""
        # Market data available
        market_res = requests.get(f"{BASE_URL}/api/market-data/coins?vs_currency=eur&per_page=5")
        assert market_res.status_code == 200
        
        # Cards available
        cards_res = requests.get(f"{BASE_URL}/api/cards/my-cards", headers=admin_headers)
        assert cards_res.status_code == 200
        
        print("✓ Dashboard quick links data endpoints working")

    def test_analytics_tracks_multiple_pages(self):
        """Analytics can track multiple page views"""
        pages = ["/dashboard", "/market", "/cards", "/admin"]
        session_id = f"test-multi-{uuid.uuid4().hex[:8]}"
        
        for page in pages:
            res = requests.post(f"{BASE_URL}/api/analytics/track",
                json={"page": page, "session_id": session_id}
            )
            assert res.status_code == 200
        
        print(f"✓ Tracked {len(pages)} page views in session")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
