"""
Phase 5 Feature Tests - NeoNoble Ramp

Tests for:
1. Multi-Chain Wallet Sync (ETH/BSC/Polygon on-chain balance reading)
2. Banking Rails (IBAN assignment, SEPA deposits/withdrawals)  
3. Enhanced Card Issuing (physical cards with shipping address and tracking)
4. Crypto-to-Fiat Payment Pipeline
5. Wallet Conversion endpoints
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_USER_EMAIL = "testchart@example.com"
TEST_USER_PASSWORD = "Test1234!"
ADMIN_USER_EMAIL = "admin@neonobleramp.com"
ADMIN_USER_PASSWORD = "Admin1234!"


@pytest.fixture(scope="module")
def test_user_token():
    """Get auth token for regular test user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Failed to login test user: {response.text}")
    return response.json().get("token")


@pytest.fixture(scope="module")
def admin_token():
    """Get auth token for admin user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_USER_EMAIL,
        "password": ADMIN_USER_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Failed to login admin user: {response.text}")
    return response.json().get("token")


@pytest.fixture
def auth_headers(test_user_token):
    """Headers with auth token"""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {test_user_token}"
    }


@pytest.fixture
def admin_headers(admin_token):
    """Headers with admin auth token"""
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {admin_token}"
    }


# =============================================================================
# 1. AUTHENTICATION TESTS
# =============================================================================
class TestAuth:
    """Test authentication endpoints"""
    
    def test_login_regular_user(self):
        """Test #1: Login with test user credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert "user" in data
        print(f"PASS: Regular user login - role: {data['user'].get('role', 'USER')}")


# =============================================================================
# 2. MULTI-CHAIN WALLET SYNC TESTS
# =============================================================================
class TestMultiChain:
    """Test Multi-Chain Wallet Sync endpoints"""
    
    def test_get_chains(self, auth_headers):
        """Test #2: GET /api/multichain/chains - Returns 3 chains"""
        response = requests.get(f"{BASE_URL}/api/multichain/chains")
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "chains" in data
        assert data["total"] >= 3, f"Expected 3+ chains, got {data['total']}"
        
        chain_keys = [c["key"] for c in data["chains"]]
        assert "ethereum" in chain_keys, "Missing ethereum chain"
        assert "bsc" in chain_keys, "Missing bsc chain"
        assert "polygon" in chain_keys, "Missing polygon chain"
        
        # Verify chain structure
        for chain in data["chains"]:
            assert "name" in chain
            assert "symbol" in chain
            assert "chain_id" in chain
            assert "connected" in chain
        
        print(f"PASS: GET /api/multichain/chains - {data['total']} chains returned")
    
    def test_link_wallet_bsc(self, auth_headers):
        """Test #3: POST /api/multichain/link - Link wallet on BSC"""
        response = requests.post(f"{BASE_URL}/api/multichain/link", 
            headers=auth_headers,
            json={
                "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18",
                "chain": "bsc"
            })
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "balances" in data
        assert data["balances"]["chain"] == "bsc"
        print(f"PASS: POST /api/multichain/link - Wallet linked on BSC")
    
    def test_get_multichain_balances(self, auth_headers):
        """Test #4: GET /api/multichain/balances - Returns linked wallets"""
        response = requests.get(f"{BASE_URL}/api/multichain/balances", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "wallets" in data
        assert "total_chains" in data
        print(f"PASS: GET /api/multichain/balances - {data['total_chains']} chain(s) synced")
    
    def test_sync_chain(self, auth_headers):
        """Test #5: POST /api/multichain/sync - Re-sync balances"""
        # First ensure wallet is linked
        requests.post(f"{BASE_URL}/api/multichain/link",
            headers=auth_headers,
            json={"address": "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18", "chain": "bsc"})
        
        response = requests.post(f"{BASE_URL}/api/multichain/sync",
            headers=auth_headers,
            json={"chain": "bsc"})
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["chain"] == "bsc"
        print(f"PASS: POST /api/multichain/sync - BSC chain synced")
    
    def test_get_linked_wallets(self, auth_headers):
        """Test #6: GET /api/multichain/linked - Get all linked addresses"""
        response = requests.get(f"{BASE_URL}/api/multichain/linked", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "linked_addresses" in data
        assert "total" in data
        print(f"PASS: GET /api/multichain/linked - {data['total']} linked address(es)")


# =============================================================================
# 3. BANKING RAILS TESTS (IBAN / SEPA)
# =============================================================================
class TestBanking:
    """Test Banking Rails (IBAN/SEPA) endpoints"""
    
    def test_assign_iban(self, auth_headers):
        """Test #7: POST /api/banking/iban/assign - Assign virtual IBAN"""
        response = requests.post(f"{BASE_URL}/api/banking/iban/assign",
            headers=auth_headers,
            json={"currency": "EUR", "beneficiary_name": "Test User"})
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "iban" in data
        iban_data = data["iban"]
        assert iban_data.get("iban") or data.get("message")
        assert iban_data.get("currency") == "EUR" or "gia' assegnato" in data.get("message", "").lower()
        print(f"PASS: POST /api/banking/iban/assign - IBAN assigned/exists")
    
    def test_get_ibans(self, auth_headers):
        """Test #8: GET /api/banking/iban - List user IBANs"""
        response = requests.get(f"{BASE_URL}/api/banking/iban", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "ibans" in data
        assert "total" in data
        print(f"PASS: GET /api/banking/iban - {data['total']} IBAN(s)")
    
    def test_sepa_deposit(self, auth_headers):
        """Test #9: POST /api/banking/sepa/deposit - SEPA deposit"""
        response = requests.post(f"{BASE_URL}/api/banking/sepa/deposit",
            headers=auth_headers,
            json={
                "amount": 500,
                "sender_iban": "IT60X0542811101000000123456",
                "sender_name": "Mario Rossi"
            })
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "transaction" in data
        tx = data["transaction"]
        assert tx["type"] == "sepa_deposit"
        assert tx["amount"] == 500
        assert tx["status"] == "completed"
        print(f"PASS: POST /api/banking/sepa/deposit - EUR {tx['amount']} deposited")
    
    def test_sepa_withdraw(self, auth_headers):
        """Test #10: POST /api/banking/sepa/withdraw - SEPA withdrawal"""
        response = requests.post(f"{BASE_URL}/api/banking/sepa/withdraw",
            headers=auth_headers,
            json={
                "amount": 50,
                "destination_iban": "IT60X0542811101000000123456",
                "beneficiary_name": "Test User"
            })
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "transaction" in data
        tx = data["transaction"]
        assert tx["type"] == "sepa_withdrawal"
        assert tx["status"] == "processing"
        assert "fee" in tx
        print(f"PASS: POST /api/banking/sepa/withdraw - EUR {tx['amount']} withdrawal initiated")
    
    def test_banking_transactions(self, auth_headers):
        """Test #11: GET /api/banking/transactions - Transaction history"""
        response = requests.get(f"{BASE_URL}/api/banking/transactions", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "transactions" in data
        assert "total" in data
        print(f"PASS: GET /api/banking/transactions - {data['total']} transaction(s)")
    
    def test_banking_admin_overview(self, admin_headers):
        """Test #12: GET /api/banking/admin/overview - Admin banking stats"""
        response = requests.get(f"{BASE_URL}/api/banking/admin/overview", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "ibans" in data
        assert "transactions" in data
        print(f"PASS: GET /api/banking/admin/overview - Admin stats retrieved")
    
    def test_banking_admin_forbidden_for_user(self, auth_headers):
        """Test #12b: Verify admin endpoint returns 403 for regular user"""
        response = requests.get(f"{BASE_URL}/api/banking/admin/overview", headers=auth_headers)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("PASS: Admin banking endpoint correctly returns 403 for regular user")


# =============================================================================
# 4. ENHANCED CARD ISSUING TESTS (Physical with Shipping)
# =============================================================================
class TestEnhancedCards:
    """Test Enhanced Card Issuing with shipping"""
    
    def test_create_physical_card_requires_address(self, auth_headers):
        """Test #13: Physical card requires shipping_address"""
        response = requests.post(f"{BASE_URL}/api/cards/create",
            headers=auth_headers,
            json={
                "card_type": "physical",
                "card_network": "visa",
                "currency": "EUR"
            })
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        assert "indirizzo" in response.text.lower() or "shipping" in response.text.lower()
        print("PASS: Physical card without shipping_address returns 400")
    
    def test_create_physical_card_with_shipping(self, auth_headers):
        """Test #13b: Create physical card with shipping address"""
        response = requests.post(f"{BASE_URL}/api/cards/create",
            headers=auth_headers,
            json={
                "card_type": "physical",
                "card_network": "visa",
                "currency": "EUR",
                "shipping_address": {
                    "line1": "Via Dante 5",
                    "city": "Roma",
                    "zip": "00100",
                    "country": "IT"
                }
            })
        if response.status_code == 400 and "maximum" in response.text.lower():
            print("PASS: Physical card creation hit max limit (expected)")
            pytest.skip("Max card limit reached")
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        card = data["card"]
        assert card["card_type"] == "physical"
        assert card["status"] == "pending_shipment"
        assert "tracking_number" in card
        assert card["tracking_number"].startswith("NN-")
        assert "shipping_address" in card
        print(f"PASS: Physical card created with tracking: {card['tracking_number']}")
        return card["id"]
    
    def test_create_virtual_card(self, auth_headers):
        """Test #14: Create virtual card (no shipping needed)"""
        response = requests.post(f"{BASE_URL}/api/cards/create",
            headers=auth_headers,
            json={
                "card_type": "virtual",
                "card_network": "mastercard",
                "currency": "EUR"
            })
        if response.status_code == 400 and "maximum" in response.text.lower():
            print("PASS: Virtual card creation hit max limit (expected)")
            pytest.skip("Max card limit reached")
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        card = data["card"]
        assert card["card_type"] == "virtual"
        assert card["status"] == "active"
        assert "tracking_number" not in card or card.get("tracking_number") is None
        print(f"PASS: Virtual card created - status: {card['status']}")
        return card["id"]
    
    def test_get_shipping_status(self, auth_headers):
        """Test #15: GET /api/cards/{card_id}/shipping - Shipping status"""
        # First get user's cards
        cards_resp = requests.get(f"{BASE_URL}/api/cards/my-cards", headers=auth_headers)
        cards = cards_resp.json().get("cards", [])
        
        physical_cards = [c for c in cards if c.get("card_type") == "physical"]
        if not physical_cards:
            print("SKIP: No physical cards to test shipping status")
            pytest.skip("No physical cards available")
        
        card_id = physical_cards[0]["id"]
        response = requests.get(f"{BASE_URL}/api/cards/{card_id}/shipping", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "shipping_status" in data
        assert "tracking_number" in data
        print(f"PASS: GET /api/cards/{card_id}/shipping - Status: {data['shipping_status']}")


# =============================================================================
# 5. CARD TOP-UP AND FUND FROM CRYPTO TESTS
# =============================================================================
class TestCardFunding:
    """Test Card top-up and crypto-to-fiat funding pipeline"""
    
    def test_card_topup(self, auth_headers):
        """Test #16: POST /api/cards/{card_id}/top-up - Top-up with crypto"""
        # Get user's cards
        cards_resp = requests.get(f"{BASE_URL}/api/cards/my-cards", headers=auth_headers)
        cards = cards_resp.json().get("cards", [])
        
        active_cards = [c for c in cards if c.get("status") == "active"]
        if not active_cards:
            print("SKIP: No active cards to top-up")
            pytest.skip("No active cards available")
        
        card_id = active_cards[0]["id"]
        response = requests.post(f"{BASE_URL}/api/cards/{card_id}/top-up",
            headers=auth_headers,
            json={"amount_crypto": 0.001, "crypto_asset": "BTC"})
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "transaction" in data
        assert "new_balance" in data
        print(f"PASS: Card top-up - new balance: €{data['new_balance']}")
    
    def test_fund_card_from_crypto(self, auth_headers):
        """Test #17: POST /api/wallet/fund-card - Crypto-to-fiat-to-card pipeline"""
        # Get user's cards
        cards_resp = requests.get(f"{BASE_URL}/api/cards/my-cards", headers=auth_headers)
        cards = cards_resp.json().get("cards", [])
        
        active_cards = [c for c in cards if c.get("status") == "active"]
        if not active_cards:
            print("SKIP: No active cards for fund-card test")
            pytest.skip("No active cards available")
        
        # First deposit some crypto
        requests.post(f"{BASE_URL}/api/wallet/deposit",
            headers=auth_headers,
            json={"asset": "ETH", "amount": 0.01})
        
        card_id = active_cards[0]["id"]
        response = requests.post(f"{BASE_URL}/api/wallet/fund-card",
            headers=auth_headers,
            json={
                "card_id": card_id,
                "crypto_asset": "ETH",
                "crypto_amount": 0.001
            })
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "fiat_amount" in data or "card_balance" in data
        print(f"PASS: Fund card from crypto - Pipeline executed")


# =============================================================================
# 6. WALLET CONVERSION TESTS
# =============================================================================
class TestWalletConversion:
    """Test Wallet conversion endpoints"""
    
    def test_convert_crypto_to_fiat(self, auth_headers):
        """Test #18a: POST /api/wallet/convert - Crypto to Fiat"""
        # First deposit
        requests.post(f"{BASE_URL}/api/wallet/deposit",
            headers=auth_headers,
            json={"asset": "NENO", "amount": 0.001})
        
        response = requests.post(f"{BASE_URL}/api/wallet/convert",
            headers=auth_headers,
            json={
                "from_asset": "NENO",
                "to_asset": "EUR",
                "amount": 0.0001
            })
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "to_amount_net" in data or "to_amount" in data
        print(f"PASS: NENO → EUR conversion")
    
    def test_convert_crypto_to_crypto(self, auth_headers):
        """Test #18b: POST /api/wallet/convert - Crypto to Crypto"""
        requests.post(f"{BASE_URL}/api/wallet/deposit",
            headers=auth_headers,
            json={"asset": "BTC", "amount": 0.001})
        
        response = requests.post(f"{BASE_URL}/api/wallet/convert",
            headers=auth_headers,
            json={
                "from_asset": "BTC",
                "to_asset": "ETH",
                "amount": 0.0001
            })
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "to_amount_net" in data or "to_amount" in data
        print(f"PASS: BTC → ETH conversion")
    
    def test_convert_fiat_to_crypto(self, auth_headers):
        """Test #18c: POST /api/wallet/convert - Fiat to Crypto"""
        # Ensure EUR balance
        requests.post(f"{BASE_URL}/api/banking/sepa/deposit",
            headers=auth_headers,
            json={"amount": 100, "sender_iban": "IT60X0542811101000000123456", "sender_name": "Test"})
        
        response = requests.post(f"{BASE_URL}/api/wallet/convert",
            headers=auth_headers,
            json={
                "from_asset": "EUR",
                "to_asset": "BTC",
                "amount": 10
            })
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "to_amount_net" in data or "to_amount" in data
        print(f"PASS: EUR → BTC conversion")


# =============================================================================
# 7. WALLET BALANCES AND SETTLEMENTS
# =============================================================================
class TestWalletBalances:
    """Test wallet balance and settlement endpoints"""
    
    def test_get_wallet_balances(self, auth_headers):
        """Test: GET /api/wallet/balances"""
        response = requests.get(f"{BASE_URL}/api/wallet/balances", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "wallets" in data
        assert "total_eur_value" in data
        print(f"PASS: GET /api/wallet/balances - Total: €{data['total_eur_value']}")
    
    def test_get_conversion_rates(self, auth_headers):
        """Test: GET /api/wallet/conversion-rates"""
        response = requests.get(f"{BASE_URL}/api/wallet/conversion-rates", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "rates" in data
        assert "supported_assets" in data
        print(f"PASS: GET /api/wallet/conversion-rates - {len(data['supported_assets'])} assets")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
