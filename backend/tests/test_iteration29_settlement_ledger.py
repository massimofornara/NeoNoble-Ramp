"""
Iteration 29 - Settlement Ledger, Payout Queue, Force Sync, Reconciliation Tests

Tests the new features:
1. Login: POST /api/auth/login with admin@neonobleramp.com / Admin1234!
2. Sell: POST /api/neno-exchange/sell - should return state='internal_credited' and debit NENO
3. Swap: POST /api/neno-exchange/swap - should return state='internal_credited' and debit NENO
4. Offramp: POST /api/neno-exchange/offramp - should return state='payout_pending' with payout object
5. Force Sync: POST /api/neno-exchange/force-balance-sync - test with existing tx hash
6. Ledger: GET /api/neno-exchange/ledger - should return entries with proper states
7. Payouts: GET /api/neno-exchange/payouts - should return payout queue entries
8. Reconcile: POST /api/neno-exchange/reconcile - should work for admin
9. Live Balances: GET /api/neno-exchange/live-balances - should return up-to-date balances
10. REGRESSION: POST /api/neno-exchange/buy, create-token, buy-custom-token
"""

import pytest
import requests
import os
import time
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-chain-wallet-14.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"

# Known tx hash for force sync test (from problem statement)
KNOWN_TX_HASH = "0x0a13928c9a8ac9f05c2d3e86ac2d58f0f949cde2bc64f8a42b6acd2703ff6d85"


class TestIteration29SettlementLedger:
    """Tests for settlement ledger, payout queue, force sync, and reconciliation features."""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for admin user."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        # API returns 'token' not 'access_token'
        token = data.get("access_token") or data.get("token")
        assert token, f"No token in response: {data}"
        return token
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get authorization headers."""
        return {"Authorization": f"Bearer {auth_token}"}
    
    # ── Test 1: Login ──
    def test_01_login_success(self):
        """Test login with admin credentials returns token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        # API returns 'token' not 'access_token'
        token = data.get("access_token") or data.get("token")
        assert token, f"No token in response: {data}"
        assert len(token) > 0, "Token is empty"
        print(f"✓ Login successful, token length: {len(token)}")
    
    # ── Test 2: Deposit EUR for testing ──
    def test_02_deposit_eur_for_testing(self, auth_headers):
        """Deposit EUR to have funds for testing."""
        response = requests.post(
            f"{BASE_URL}/api/wallet/deposit",
            json={"asset": "EUR", "amount": 5000},
            headers=auth_headers
        )
        # Accept 200 or 201
        assert response.status_code in [200, 201], f"Deposit failed: {response.text}"
        data = response.json()
        print(f"✓ EUR deposit: {data.get('message', data)}")
    
    # ── Test 3: Buy NENO to have balance for sell/swap/offramp tests ──
    def test_03_buy_neno_for_testing(self, auth_headers):
        """Buy NENO to have balance for subsequent tests."""
        time.sleep(0.5)  # Rate limit cooldown
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/buy",
            json={"pay_asset": "EUR", "neno_amount": 5},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Buy NENO failed: {response.text}"
        data = response.json()
        assert "transaction" in data, f"No transaction in response: {data}"
        assert data["transaction"]["type"] == "buy_neno"
        print(f"✓ Bought NENO: {data.get('message', '')}")
    
    # ── Test 4: Sell NENO - should return state='internal_credited' ──
    def test_04_sell_neno_returns_internal_credited_state(self, auth_headers):
        """Sell NENO should return state='internal_credited' and debit NENO."""
        time.sleep(0.5)
        
        # Get initial balance
        bal_resp = requests.get(f"{BASE_URL}/api/wallet/balances", headers=auth_headers)
        initial_balances = {w["asset"]: w["balance"] for w in bal_resp.json().get("wallets", [])}
        initial_neno = initial_balances.get("NENO", 0)
        
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/sell",
            json={"receive_asset": "EUR", "neno_amount": 2},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Sell failed: {response.text}"
        data = response.json()
        
        # Check state is returned
        assert "state" in data, f"No 'state' in sell response: {data}"
        assert data["state"] == "internal_credited", f"Expected state='internal_credited', got: {data['state']}"
        
        # Check NENO was debited
        assert "balances" in data, f"No balances in response: {data}"
        new_neno = data["balances"].get("NENO", 0)
        assert new_neno < initial_neno, f"NENO not debited: initial={initial_neno}, new={new_neno}"
        
        print(f"✓ Sell NENO: state={data['state']}, NENO debited from {initial_neno} to {new_neno}")
    
    # ── Test 5: Swap NENO→ETH - should return state='internal_credited' ──
    def test_05_swap_neno_returns_internal_credited_state(self, auth_headers):
        """Swap NENO→ETH should return state='internal_credited' and debit NENO."""
        time.sleep(0.5)
        
        # Get initial balance
        bal_resp = requests.get(f"{BASE_URL}/api/wallet/balances", headers=auth_headers)
        initial_balances = {w["asset"]: w["balance"] for w in bal_resp.json().get("wallets", [])}
        initial_neno = initial_balances.get("NENO", 0)
        
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/swap",
            json={"from_asset": "NENO", "to_asset": "ETH", "amount": 1},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Swap failed: {response.text}"
        data = response.json()
        
        # Check state is returned
        assert "state" in data, f"No 'state' in swap response: {data}"
        assert data["state"] == "internal_credited", f"Expected state='internal_credited', got: {data['state']}"
        
        # Check NENO was debited
        assert "balances" in data, f"No balances in response: {data}"
        new_neno = data["balances"].get("NENO", 0)
        assert new_neno < initial_neno, f"NENO not debited: initial={initial_neno}, new={new_neno}"
        
        print(f"✓ Swap NENO→ETH: state={data['state']}, NENO debited from {initial_neno} to {new_neno}")
    
    # ── Test 6: Offramp NENO to bank - should return state='payout_pending' with payout object ──
    def test_06_offramp_neno_returns_payout_pending_state(self, auth_headers):
        """Offramp NENO to bank should return state='payout_pending' with payout object."""
        time.sleep(0.5)
        
        # Get initial balance
        bal_resp = requests.get(f"{BASE_URL}/api/wallet/balances", headers=auth_headers)
        initial_balances = {w["asset"]: w["balance"] for w in bal_resp.json().get("wallets", [])}
        initial_neno = initial_balances.get("NENO", 0)
        
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/offramp",
            json={
                "neno_amount": 1,
                "destination": "bank",
                "destination_iban": "IT60X0542811101000000123456",
                "beneficiary_name": "Test User"
            },
            headers=auth_headers
        )
        assert response.status_code == 200, f"Offramp failed: {response.text}"
        data = response.json()
        
        # Check state is payout_pending for bank transfers
        assert "state" in data, f"No 'state' in offramp response: {data}"
        assert data["state"] == "payout_pending", f"Expected state='payout_pending', got: {data['state']}"
        
        # Check payout object is returned
        assert "payout" in data, f"No 'payout' in offramp response: {data}"
        payout = data["payout"]
        assert payout.get("id") is not None, f"Payout has no id: {payout}"
        assert payout.get("state") == "payout_pending", f"Payout state mismatch: {payout}"
        
        # Check NENO was debited
        new_neno = data.get("neno_balance", 0)
        assert new_neno < initial_neno, f"NENO not debited: initial={initial_neno}, new={new_neno}"
        
        print(f"✓ Offramp NENO: state={data['state']}, payout_id={payout.get('id')[:8]}..., NENO debited")
    
    # ── Test 7: Force Balance Sync with known tx hash ──
    def test_07_force_balance_sync(self, auth_headers):
        """Force sync with existing tx hash should return already synced message."""
        time.sleep(0.5)
        
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/force-balance-sync",
            json={"tx_hash": KNOWN_TX_HASH},
            headers=auth_headers
        )
        
        # Should return 200 with "already synced" message or success
        assert response.status_code == 200, f"Force sync failed: {response.text}"
        data = response.json()
        
        # Check response has expected fields
        assert "message" in data, f"No message in force sync response: {data}"
        assert "tx_hash" in data, f"No tx_hash in response: {data}"
        
        # Message should indicate already synced or success
        msg = data["message"].lower()
        assert "sincronizzat" in msg or "synced" in msg.lower() or "accreditati" in msg, \
            f"Unexpected message: {data['message']}"
        
        print(f"✓ Force sync: {data['message']}")
    
    # ── Test 8: Get Ledger entries ──
    def test_08_get_ledger_entries(self, auth_headers):
        """GET /api/neno-exchange/ledger should return entries with proper states."""
        time.sleep(0.5)
        
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/ledger",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Get ledger failed: {response.text}"
        data = response.json()
        
        assert "entries" in data, f"No 'entries' in ledger response: {data}"
        assert "total" in data, f"No 'total' in ledger response: {data}"
        
        entries = data["entries"]
        print(f"✓ Ledger: {data['total']} entries found")
        
        # If there are entries, verify structure
        if len(entries) > 0:
            entry = entries[0]
            assert "id" in entry, f"Entry missing 'id': {entry}"
            assert "state" in entry, f"Entry missing 'state': {entry}"
            assert "type" in entry, f"Entry missing 'type': {entry}"
            
            # Check state is valid
            valid_states = ["on_chain_executed", "internal_credited", "payout_pending", "payout_sent", "payout_settled", "payout_failed"]
            assert entry["state"] in valid_states, f"Invalid state: {entry['state']}"
            
            print(f"  First entry: type={entry['type']}, state={entry['state']}")
    
    # ── Test 9: Get Payouts queue ──
    def test_09_get_payouts_queue(self, auth_headers):
        """GET /api/neno-exchange/payouts should return payout queue entries."""
        time.sleep(0.5)
        
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/payouts",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Get payouts failed: {response.text}"
        data = response.json()
        
        assert "payouts" in data, f"No 'payouts' in response: {data}"
        assert "total" in data, f"No 'total' in response: {data}"
        
        payouts = data["payouts"]
        print(f"✓ Payouts: {data['total']} entries found")
        
        # If there are payouts, verify structure
        if len(payouts) > 0:
            payout = payouts[0]
            assert "id" in payout, f"Payout missing 'id': {payout}"
            assert "state" in payout, f"Payout missing 'state': {payout}"
            assert "amount" in payout, f"Payout missing 'amount': {payout}"
            
            print(f"  First payout: amount={payout['amount']}, state={payout['state']}")
    
    # ── Test 10: Reconcile (admin only) ──
    def test_10_reconcile_admin(self, auth_headers):
        """POST /api/neno-exchange/reconcile should work for admin."""
        time.sleep(0.5)
        
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/reconcile",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Reconcile failed: {response.text}"
        data = response.json()
        
        assert "reconciled_credits" in data, f"No 'reconciled_credits' in response: {data}"
        assert "unmatched_deposits" in data, f"No 'unmatched_deposits' in response: {data}"
        
        print(f"✓ Reconcile: {data['reconciled_credits']} credits, {data['unmatched_deposits']} unmatched")
    
    # ── Test 11: Live Balances ──
    def test_11_live_balances(self, auth_headers):
        """GET /api/neno-exchange/live-balances should return up-to-date balances with USD values."""
        time.sleep(0.5)
        
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/live-balances",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Live balances failed: {response.text}"
        data = response.json()
        
        assert "balances" in data, f"No 'balances' in response: {data}"
        assert "total_value_usd" in data, f"No 'total_value_usd' in response: {data}"
        assert "neno_price" in data, f"No 'neno_price' in response: {data}"
        assert "timestamp" in data, f"No 'timestamp' in response: {data}"
        
        balances = data["balances"]
        print(f"✓ Live balances: {len(balances)} assets, total USD: ${data['total_value_usd']}")
        
        # Check balance structure
        for asset, info in list(balances.items())[:3]:
            assert "balance" in info, f"Balance missing 'balance': {info}"
            assert "price_usd" in info, f"Balance missing 'price_usd': {info}"
            assert "value_usd" in info, f"Balance missing 'value_usd': {info}"
            print(f"  {asset}: {info['balance']} (${info['value_usd']})")
    
    # ── REGRESSION Test 12: Buy NENO still works ──
    def test_12_regression_buy_neno(self, auth_headers):
        """REGRESSION: POST /api/neno-exchange/buy should still work."""
        time.sleep(0.5)
        
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/buy",
            json={"pay_asset": "EUR", "neno_amount": 0.5},
            headers=auth_headers
        )
        assert response.status_code == 200, f"Buy NENO failed: {response.text}"
        data = response.json()
        assert "transaction" in data, f"No transaction in response: {data}"
        assert data["transaction"]["type"] == "buy_neno"
        print(f"✓ REGRESSION: Buy NENO works")
    
    # ── REGRESSION Test 13: Create Token still works ──
    def test_13_regression_create_token(self, auth_headers):
        """REGRESSION: POST /api/neno-exchange/create-token should still work."""
        time.sleep(0.5)
        
        unique_symbol = f"T{uuid.uuid4().hex[:5].upper()}"
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/create-token",
            json={
                "symbol": unique_symbol,
                "name": f"Test Token {unique_symbol}",
                "price_usd": 1.50,
                "total_supply": 10000
            },
            headers=auth_headers
        )
        assert response.status_code == 200, f"Create token failed: {response.text}"
        data = response.json()
        assert "token" in data, f"No token in response: {data}"
        assert data["token"]["symbol"] == unique_symbol
        print(f"✓ REGRESSION: Create token works ({unique_symbol})")
    
    # ── REGRESSION Test 14: Buy Custom Token still works ──
    def test_14_regression_buy_custom_token(self, auth_headers):
        """REGRESSION: POST /api/neno-exchange/buy-custom-token should still work."""
        time.sleep(0.5)
        
        # First create a token to buy
        unique_symbol = f"B{uuid.uuid4().hex[:5].upper()}"
        create_resp = requests.post(
            f"{BASE_URL}/api/neno-exchange/create-token",
            json={
                "symbol": unique_symbol,
                "name": f"Buy Test Token {unique_symbol}",
                "price_usd": 0.50,
                "total_supply": 10000
            },
            headers=auth_headers
        )
        assert create_resp.status_code == 200, f"Create token failed: {create_resp.text}"
        
        time.sleep(0.3)
        
        # Now buy some of it
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/buy-custom-token",
            json={
                "symbol": unique_symbol,
                "amount": 10,
                "pay_asset": "EUR"
            },
            headers=auth_headers
        )
        assert response.status_code == 200, f"Buy custom token failed: {response.text}"
        data = response.json()
        assert "transaction" in data, f"No transaction in response: {data}"
        print(f"✓ REGRESSION: Buy custom token works ({unique_symbol})")


class TestIteration29FrontendElements:
    """Frontend verification tests using API to check data availability."""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for admin user."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        return data.get("access_token") or data.get("token")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}"}
    
    def test_platform_wallet_available(self, auth_headers):
        """Platform wallet endpoint should return address for deposit widget."""
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/platform-wallet",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Platform wallet failed: {response.text}"
        data = response.json()
        assert "address" in data, f"No address in response: {data}"
        assert data["address"].startswith("0x"), f"Invalid address format: {data['address']}"
        print(f"✓ Platform wallet: {data['address'][:10]}...")
    
    def test_market_info_available(self):
        """Market info endpoint should return NENO price and pairs."""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/market")
        assert response.status_code == 200, f"Market info failed: {response.text}"
        data = response.json()
        assert "neno_eur_price" in data, f"No neno_eur_price: {data}"
        assert "pairs" in data, f"No pairs: {data}"
        print(f"✓ Market info: NENO @ EUR {data['neno_eur_price']}")
    
    def test_price_endpoint_available(self):
        """Price endpoint should return dynamic NENO price."""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/price")
        assert response.status_code == 200, f"Price failed: {response.text}"
        data = response.json()
        assert "neno_eur_price" in data, f"No neno_eur_price: {data}"
        assert "pricing_model" in data, f"No pricing_model: {data}"
        print(f"✓ Price: EUR {data['neno_eur_price']} ({data['pricing_model']})")
    
    def test_my_tokens_endpoint(self, auth_headers):
        """My tokens endpoint should return user's custom tokens."""
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/my-tokens",
            headers=auth_headers
        )
        assert response.status_code == 200, f"My tokens failed: {response.text}"
        data = response.json()
        assert "tokens" in data, f"No tokens in response: {data}"
        assert "total" in data, f"No total in response: {data}"
        print(f"✓ My tokens: {data['total']} tokens")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
