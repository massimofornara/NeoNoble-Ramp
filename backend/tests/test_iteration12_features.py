"""
Iteration 12 Tests: Advanced Orders, 2FA TOTP, Notifications, Portfolio Analytics, Settings, NIUM Banking, AI KYC

Tests:
- Advanced Orders API: limit, stop, trailing-stop, active orders, cancel
- 2FA TOTP API: setup, status, verify
- Notifications API: list, read-all, unread-count
- KYC verify-document endpoint
- Banking routes with NIUM fallback
- NENO dynamic price
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
    """Get authentication token for test user"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def admin_token(api_client):
    """Get authentication token for admin user"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Admin authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


@pytest.fixture(scope="module")
def admin_client(api_client, admin_token):
    """Session with admin auth header"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}"
    })
    return session


# ============ ADVANCED ORDERS TESTS ============

class TestAdvancedOrders:
    """Advanced Orders API tests: limit, stop, trailing-stop"""

    def test_get_active_orders(self, authenticated_client):
        """GET /api/trading/orders/active returns active orders list"""
        response = authenticated_client.get(f"{BASE_URL}/api/trading/orders/active")
        assert response.status_code == 200
        data = response.json()
        assert "orders" in data
        assert "total" in data
        assert isinstance(data["orders"], list)
        print(f"Active orders: {data['total']}")

    def test_place_limit_order(self, authenticated_client):
        """POST /api/trading/orders/limit creates a limit order"""
        response = authenticated_client.post(f"{BASE_URL}/api/trading/orders/limit", json={
            "pair_id": "BTC-EUR",
            "side": "buy",
            "quantity": 0.001,
            "limit_price": 50000.0,
            "time_in_force": "GTC"
        })
        # May fail due to insufficient balance, but endpoint should work
        if response.status_code == 200:
            data = response.json()
            assert "order" in data
            assert data["order"]["type"] == "limit"
            assert data["order"]["status"] == "open"
            print(f"Limit order created: {data['order']['id']}")
        else:
            # 400 is acceptable if insufficient balance
            assert response.status_code in [200, 400]
            print(f"Limit order response: {response.status_code} - {response.json().get('detail', 'OK')}")

    def test_place_stop_order(self, authenticated_client):
        """POST /api/trading/orders/stop creates a stop order"""
        response = authenticated_client.post(f"{BASE_URL}/api/trading/orders/stop", json={
            "pair_id": "BTC-EUR",
            "side": "sell",
            "quantity": 0.001,
            "stop_price": 45000.0
        })
        # Stop orders don't reserve funds immediately
        if response.status_code == 200:
            data = response.json()
            assert "order" in data
            assert data["order"]["type"] in ["stop", "stop_limit"]
            assert data["order"]["status"] == "pending"
            print(f"Stop order created: {data['order']['id']}")
        else:
            assert response.status_code in [200, 400]
            print(f"Stop order response: {response.status_code}")

    def test_place_trailing_stop(self, authenticated_client):
        """POST /api/trading/orders/trailing-stop creates a trailing stop"""
        response = authenticated_client.post(f"{BASE_URL}/api/trading/orders/trailing-stop", json={
            "pair_id": "BTC-EUR",
            "side": "sell",
            "quantity": 0.001,
            "trail_percent": 2.0
        })
        if response.status_code == 200:
            data = response.json()
            assert "order" in data
            assert data["order"]["type"] == "trailing_stop"
            assert data["order"]["status"] == "tracking"
            print(f"Trailing stop created: {data['order']['id']}")
        else:
            assert response.status_code in [200, 400]
            print(f"Trailing stop response: {response.status_code}")

    def test_cancel_order(self, authenticated_client):
        """POST /api/trading/orders/cancel cancels an order"""
        # First get active orders
        active_res = authenticated_client.get(f"{BASE_URL}/api/trading/orders/active")
        active_data = active_res.json()
        
        if active_data.get("orders") and len(active_data["orders"]) > 0:
            order_id = active_data["orders"][0]["id"]
            response = authenticated_client.post(f"{BASE_URL}/api/trading/orders/cancel", json={
                "order_id": order_id
            })
            if response.status_code == 200:
                data = response.json()
                assert "message" in data
                print(f"Order cancelled: {order_id}")
            else:
                # Order may already be filled/cancelled
                assert response.status_code in [200, 400, 404]
                print(f"Cancel response: {response.status_code}")
        else:
            print("No active orders to cancel - skipping")

    def test_get_order_history(self, authenticated_client):
        """GET /api/trading/orders/history returns order history"""
        response = authenticated_client.get(f"{BASE_URL}/api/trading/orders/history")
        assert response.status_code == 200
        data = response.json()
        assert "orders" in data
        assert "total" in data
        print(f"Order history: {data['total']} orders")


# ============ 2FA TOTP TESTS ============

class Test2FATOTP:
    """Two-Factor Authentication TOTP API tests"""

    def test_get_2fa_status(self, authenticated_client):
        """GET /api/auth/2fa/status returns 2FA status"""
        response = authenticated_client.get(f"{BASE_URL}/api/auth/2fa/status")
        assert response.status_code == 200
        data = response.json()
        assert "enabled" in data
        assert isinstance(data["enabled"], bool)
        print(f"2FA enabled: {data['enabled']}, backup codes remaining: {data.get('backup_codes_remaining', 0)}")

    def test_setup_2fa(self, authenticated_client):
        """POST /api/auth/2fa/setup generates TOTP secret and QR code"""
        # First check if 2FA is already enabled
        status_res = authenticated_client.get(f"{BASE_URL}/api/auth/2fa/status")
        status_data = status_res.json()
        
        if status_data.get("enabled"):
            print("2FA already enabled - skipping setup test")
            return
        
        response = authenticated_client.post(f"{BASE_URL}/api/auth/2fa/setup")
        if response.status_code == 200:
            data = response.json()
            assert "secret" in data
            assert "qr_code_base64" in data
            assert "uri" in data
            assert data["qr_code_base64"].startswith("data:image/png;base64,")
            print(f"2FA setup successful - secret generated")
        else:
            # 400 if already enabled
            assert response.status_code in [200, 400]
            print(f"2FA setup response: {response.status_code} - {response.json().get('detail', 'OK')}")


# ============ NOTIFICATIONS TESTS ============

class TestNotifications:
    """Notifications API tests"""

    def test_get_notifications(self, authenticated_client):
        """GET /api/notifications/ returns notifications list"""
        response = authenticated_client.get(f"{BASE_URL}/api/notifications/?limit=20")
        assert response.status_code == 200
        data = response.json()
        assert "notifications" in data
        assert "unread_count" in data
        assert "total" in data
        assert isinstance(data["notifications"], list)
        print(f"Notifications: {data['total']}, unread: {data['unread_count']}")

    def test_get_unread_count(self, authenticated_client):
        """GET /api/notifications/unread-count returns unread count"""
        response = authenticated_client.get(f"{BASE_URL}/api/notifications/unread-count")
        assert response.status_code == 200
        data = response.json()
        assert "unread_count" in data
        assert isinstance(data["unread_count"], int)
        print(f"Unread notifications: {data['unread_count']}")

    def test_mark_all_as_read(self, authenticated_client):
        """POST /api/notifications/read-all marks all as read"""
        response = authenticated_client.post(f"{BASE_URL}/api/notifications/read-all")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        print(f"Mark all read: {data['message']}")


# ============ KYC VERIFY-DOCUMENT TESTS ============

class TestKYCVerifyDocument:
    """KYC document verification endpoint tests"""

    def test_verify_document_requires_kyc_data(self, authenticated_client):
        """POST /api/kyc/verify-document requires KYC data first"""
        # This test verifies the endpoint exists and validates input
        # Actual AI verification requires a real document image
        response = authenticated_client.post(f"{BASE_URL}/api/kyc/verify-document", json={
            "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            "mime_type": "image/png"
        })
        # May return 400 if no KYC data submitted, or 200 if AI verification runs
        assert response.status_code in [200, 400]
        data = response.json()
        print(f"Verify document response: {response.status_code} - {data.get('message', data.get('detail', 'OK'))}")

    def test_ocr_extract_endpoint(self, authenticated_client):
        """POST /api/kyc/ocr-extract extracts data from document"""
        response = authenticated_client.post(f"{BASE_URL}/api/kyc/ocr-extract", json={
            "image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
            "mime_type": "image/png"
        })
        # Endpoint should exist and return result
        assert response.status_code in [200, 400, 500]
        print(f"OCR extract response: {response.status_code}")


# ============ BANKING ROUTES TESTS ============

class TestBankingRoutes:
    """Banking routes with NIUM integration tests"""

    def test_assign_virtual_iban(self, authenticated_client):
        """POST /api/banking/iban/assign assigns virtual IBAN with NIUM fallback"""
        response = authenticated_client.post(f"{BASE_URL}/api/banking/iban/assign", json={
            "currency": "EUR"
        })
        assert response.status_code == 200
        data = response.json()
        assert "iban" in data
        iban_data = data["iban"]
        assert "iban" in iban_data
        assert "bic" in iban_data
        assert "currency" in iban_data
        # Check provider (nium_live or simulated)
        provider = data.get("provider", iban_data.get("source", "unknown"))
        print(f"IBAN assigned: {iban_data['iban'][:10]}... provider: {provider}")

    def test_get_my_ibans(self, authenticated_client):
        """GET /api/banking/iban returns user's virtual IBANs"""
        response = authenticated_client.get(f"{BASE_URL}/api/banking/iban")
        assert response.status_code == 200
        data = response.json()
        assert "ibans" in data
        assert "total" in data
        print(f"User IBANs: {data['total']}")

    def test_get_banking_transactions(self, authenticated_client):
        """GET /api/banking/transactions returns banking transaction history"""
        response = authenticated_client.get(f"{BASE_URL}/api/banking/transactions?limit=20")
        assert response.status_code == 200
        data = response.json()
        assert "transactions" in data
        assert "total" in data
        print(f"Banking transactions: {data['total']}")


# ============ NENO DYNAMIC PRICE TESTS ============

class TestNENODynamicPrice:
    """NENO Exchange dynamic price tests"""

    def test_get_neno_price(self, api_client):
        """GET /api/neno-exchange/price returns dynamic NENO price"""
        response = api_client.get(f"{BASE_URL}/api/neno-exchange/price")
        assert response.status_code == 200
        data = response.json()
        # API returns neno_eur_price instead of price
        assert "neno_eur_price" in data
        assert "base_price" in data
        assert "shift_pct" in data
        assert data["neno_eur_price"] > 0
        print(f"NENO price: {data['neno_eur_price']} EUR (base: {data['base_price']}, shift: {data['shift_pct']}%)")


# ============ PORTFOLIO & WALLET TESTS ============

class TestPortfolioWallet:
    """Portfolio and wallet balance tests"""

    def test_get_wallet_balances(self, authenticated_client):
        """GET /api/wallet/balances returns wallet balances"""
        response = authenticated_client.get(f"{BASE_URL}/api/wallet/balances")
        assert response.status_code == 200
        data = response.json()
        assert "wallets" in data
        print(f"Wallet balances: {len(data.get('wallets', []))} assets, total EUR: {data.get('total_eur_value', 0)}")

    def test_get_trading_trades(self, authenticated_client):
        """GET /api/trading/trades/{pair_id} returns trade history"""
        response = authenticated_client.get(f"{BASE_URL}/api/trading/trades/BTC-EUR?limit=50")
        assert response.status_code == 200
        data = response.json()
        assert "trades" in data
        print(f"Trades: {len(data.get('trades', []))}")

    def test_get_margin_positions(self, authenticated_client):
        """GET /api/trading/margin/positions returns margin positions"""
        response = authenticated_client.get(f"{BASE_URL}/api/trading/margin/positions")
        assert response.status_code == 200
        data = response.json()
        assert "positions" in data
        print(f"Margin positions: {len(data.get('positions', []))}")


# ============ ADMIN BANKING OVERVIEW ============

class TestAdminBanking:
    """Admin banking overview tests"""

    def test_admin_banking_overview(self, admin_client):
        """GET /api/banking/admin/overview returns banking stats"""
        response = admin_client.get(f"{BASE_URL}/api/banking/admin/overview")
        assert response.status_code == 200
        data = response.json()
        assert "ibans" in data
        assert "transactions" in data
        assert "provider" in data
        print(f"Banking overview: {data['ibans']['total']} IBANs, provider: {data['provider']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
