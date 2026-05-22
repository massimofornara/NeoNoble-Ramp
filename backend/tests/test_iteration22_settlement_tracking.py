"""
Iteration 22 - Settlement Tracking & Wallet Sync Tests

Tests for:
1. POST /api/neno-exchange/buy - returns settlement_hash in transaction
2. POST /api/neno-exchange/sell - returns settlement_hash in transaction
3. POST /api/neno-exchange/swap - returns settlement_hash in transaction
4. POST /api/neno-exchange/offramp - returns settlement_hash in transaction
5. POST /api/neno-exchange/create-token - creates token successfully
6. GET /api/neno-exchange/settlement/{tx_id} - returns settlement verification
7. POST /api/neno-exchange/wallet-sync - accepts external wallet address
8. GET /api/neno-exchange/portfolio-snapshot - returns positions and settlements
9. Wallet balances update correctly after each operation
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-chain-wallet-14.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"


class TestSettlementTracking:
    """Settlement tracking tests for NENO Exchange operations"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for admin user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in login response"
        print(f"Login successful for {ADMIN_EMAIL}")
        return data["token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get auth headers"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
    
    def test_health_check(self):
        """Test API health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print("Health check: PASS")
    
    def test_buy_neno_returns_settlement_hash(self, auth_headers):
        """Test POST /api/neno-exchange/buy returns settlement_hash in transaction"""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/buy",
            headers=auth_headers,
            json={"pay_asset": "EUR", "neno_amount": 0.001}
        )
        assert response.status_code == 200, f"Buy failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "transaction" in data, "No transaction in response"
        assert "balances" in data, "No balances in response"
        assert "message" in data, "No message in response"
        
        tx = data["transaction"]
        assert "settlement_hash" in tx, "No settlement_hash in transaction"
        assert tx["settlement_hash"].startswith("0x"), "Settlement hash should start with 0x"
        assert len(tx["settlement_hash"]) == 66, "Settlement hash should be 66 chars (0x + 64 hex)"
        assert tx.get("settlement_status") == "settled", "Settlement status should be 'settled'"
        assert "settlement_timestamp" in tx, "No settlement_timestamp in transaction"
        
        print(f"BUY NENO: PASS - settlement_hash: {tx['settlement_hash'][:20]}...")
        return tx["id"]
    
    def test_sell_neno_returns_settlement_hash(self, auth_headers):
        """Test POST /api/neno-exchange/sell returns settlement_hash in transaction"""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/sell",
            headers=auth_headers,
            json={"receive_asset": "EUR", "neno_amount": 0.001}
        )
        assert response.status_code == 200, f"Sell failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "transaction" in data, "No transaction in response"
        tx = data["transaction"]
        assert "settlement_hash" in tx, "No settlement_hash in transaction"
        assert tx["settlement_hash"].startswith("0x"), "Settlement hash should start with 0x"
        assert len(tx["settlement_hash"]) == 66, "Settlement hash should be 66 chars"
        assert tx.get("settlement_status") == "settled", "Settlement status should be 'settled'"
        
        print(f"SELL NENO: PASS - settlement_hash: {tx['settlement_hash'][:20]}...")
        return tx["id"]
    
    def test_swap_returns_settlement_hash(self, auth_headers):
        """Test POST /api/neno-exchange/swap returns settlement_hash in transaction"""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/swap",
            headers=auth_headers,
            json={"from_asset": "NENO", "to_asset": "ETH", "amount": 0.001}
        )
        assert response.status_code == 200, f"Swap failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "transaction" in data, "No transaction in response"
        tx = data["transaction"]
        assert "settlement_hash" in tx, "No settlement_hash in transaction"
        assert tx["settlement_hash"].startswith("0x"), "Settlement hash should start with 0x"
        assert len(tx["settlement_hash"]) == 66, "Settlement hash should be 66 chars"
        assert tx.get("settlement_status") == "settled", "Settlement status should be 'settled'"
        
        print(f"SWAP: PASS - settlement_hash: {tx['settlement_hash'][:20]}...")
        return tx["id"]
    
    def test_offramp_returns_settlement_hash(self, auth_headers):
        """Test POST /api/neno-exchange/offramp returns settlement_hash in transaction"""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/offramp",
            headers=auth_headers,
            json={
                "neno_amount": 0.001,
                "destination": "bank",
                "destination_iban": "IT60X0542811101000000123456",
                "beneficiary_name": "Test User"
            }
        )
        assert response.status_code == 200, f"Off-ramp failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "transaction" in data, "No transaction in response"
        tx = data["transaction"]
        assert "settlement_hash" in tx, "No settlement_hash in transaction"
        assert tx["settlement_hash"].startswith("0x"), "Settlement hash should start with 0x"
        assert len(tx["settlement_hash"]) == 66, "Settlement hash should be 66 chars"
        assert tx.get("settlement_status") == "settled", "Settlement status should be 'settled'"
        
        print(f"OFF-RAMP: PASS - settlement_hash: {tx['settlement_hash'][:20]}...")
        return tx["id"]
    
    def test_create_token_success(self, auth_headers):
        """Test POST /api/neno-exchange/create-token creates token successfully"""
        unique_symbol = f"T{uuid.uuid4().hex[:5].upper()}"
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/create-token",
            headers=auth_headers,
            json={
                "symbol": unique_symbol,
                "name": f"Test Token {unique_symbol}",
                "price_eur": 0.01,
                "total_supply": 1000000
            }
        )
        assert response.status_code == 200, f"Create token failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "token" in data, "No token in response"
        assert "message" in data, "No message in response"
        assert "balance" in data, "No balance in response"
        
        token = data["token"]
        assert token["symbol"] == unique_symbol, "Token symbol mismatch"
        assert data["balance"] == 1000000, "Token balance should be total supply"
        
        print(f"CREATE TOKEN: PASS - {unique_symbol} created with 1M supply")
        return unique_symbol
    
    def test_settlement_verification_endpoint(self, auth_headers):
        """Test GET /api/neno-exchange/settlement/{tx_id} returns settlement verification"""
        # First create a transaction to get a valid tx_id
        buy_response = requests.post(
            f"{BASE_URL}/api/neno-exchange/buy",
            headers=auth_headers,
            json={"pay_asset": "EUR", "neno_amount": 0.001}
        )
        assert buy_response.status_code == 200, f"Buy failed: {buy_response.text}"
        tx_id = buy_response.json()["transaction"]["id"]
        
        # Now verify settlement
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/settlement/{tx_id}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Settlement verification failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert data.get("transaction_id") == tx_id, "Transaction ID mismatch"
        assert "settlement_hash" in data, "No settlement_hash in response"
        assert data["settlement_hash"].startswith("0x"), "Settlement hash should start with 0x"
        assert data.get("settlement_status") == "settled", "Settlement status should be 'settled'"
        assert "settlement_timestamp" in data, "No settlement_timestamp in response"
        assert data.get("settlement_network") == "NeoNoble Internal Ledger", "Wrong settlement network"
        
        print(f"SETTLEMENT VERIFICATION: PASS - tx_id: {tx_id[:8]}...")
    
    def test_settlement_verification_not_found(self, auth_headers):
        """Test GET /api/neno-exchange/settlement/{tx_id} returns 404 for invalid tx_id"""
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/settlement/invalid-tx-id-12345",
            headers=auth_headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("SETTLEMENT NOT FOUND: PASS - returns 404 for invalid tx_id")
    
    def test_wallet_sync_endpoint(self, auth_headers):
        """Test POST /api/neno-exchange/wallet-sync accepts external wallet address"""
        test_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f8fE00"
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/wallet-sync",
            headers=auth_headers,
            json={
                "external_address": test_address,
                "chain_id": 1,
                "on_chain_balances": {"ETH": 1.5, "USDT": 1000}
            }
        )
        assert response.status_code == 200, f"Wallet sync failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert data.get("external_address") == test_address, "External address mismatch"
        assert data.get("chain_id") == 1, "Chain ID mismatch"
        assert "synced_at" in data, "No synced_at in response"
        assert "internal_balances" in data, "No internal_balances in response"
        assert "sync_report" in data, "No sync_report in response"
        assert "total_internal_assets" in data, "No total_internal_assets in response"
        
        print(f"WALLET SYNC: PASS - synced {test_address[:10]}... with {data['total_internal_assets']} assets")
    
    def test_portfolio_snapshot_endpoint(self, auth_headers):
        """Test GET /api/neno-exchange/portfolio-snapshot returns positions and settlements"""
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/portfolio-snapshot",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Portfolio snapshot failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "snapshot_timestamp" in data, "No snapshot_timestamp in response"
        assert "total_value_eur" in data, "No total_value_eur in response"
        assert "positions" in data, "No positions in response"
        assert "recent_settlements" in data, "No recent_settlements in response"
        
        # Verify positions structure
        assert isinstance(data["positions"], list), "Positions should be a list"
        if len(data["positions"]) > 0:
            pos = data["positions"][0]
            assert "asset" in pos, "Position missing asset"
            assert "balance" in pos, "Position missing balance"
            assert "price_eur" in pos, "Position missing price_eur"
            assert "value_eur" in pos, "Position missing value_eur"
        
        # Verify recent_settlements structure
        assert isinstance(data["recent_settlements"], list), "Recent settlements should be a list"
        if len(data["recent_settlements"]) > 0:
            settlement = data["recent_settlements"][0]
            assert "id" in settlement, "Settlement missing id"
            assert "type" in settlement, "Settlement missing type"
            assert "settlement_hash" in settlement, "Settlement missing settlement_hash"
            assert "status" in settlement, "Settlement missing status"
        
        print(f"PORTFOLIO SNAPSHOT: PASS - {len(data['positions'])} positions, {len(data['recent_settlements'])} recent settlements")
    
    def test_wallet_balances_update_after_buy(self, auth_headers):
        """Test wallet balances update correctly after buy operation"""
        # Get initial balances
        initial_response = requests.get(
            f"{BASE_URL}/api/wallet/balances",
            headers=auth_headers
        )
        assert initial_response.status_code == 200
        initial_wallets = {w["asset"]: w["balance"] for w in initial_response.json().get("wallets", [])}
        initial_neno = initial_wallets.get("NENO", 0)
        initial_eur = initial_wallets.get("EUR", 0)
        
        # Execute buy
        buy_amount = 0.001
        buy_response = requests.post(
            f"{BASE_URL}/api/neno-exchange/buy",
            headers=auth_headers,
            json={"pay_asset": "EUR", "neno_amount": buy_amount}
        )
        assert buy_response.status_code == 200
        
        # Get updated balances
        updated_response = requests.get(
            f"{BASE_URL}/api/wallet/balances",
            headers=auth_headers
        )
        assert updated_response.status_code == 200
        updated_wallets = {w["asset"]: w["balance"] for w in updated_response.json().get("wallets", [])}
        updated_neno = updated_wallets.get("NENO", 0)
        updated_eur = updated_wallets.get("EUR", 0)
        
        # Verify NENO increased
        assert updated_neno > initial_neno, f"NENO balance should increase: {initial_neno} -> {updated_neno}"
        # Verify EUR decreased
        assert updated_eur < initial_eur, f"EUR balance should decrease: {initial_eur} -> {updated_eur}"
        
        print(f"BALANCE UPDATE (BUY): PASS - NENO: {initial_neno:.4f} -> {updated_neno:.4f}, EUR: {initial_eur:.2f} -> {updated_eur:.2f}")
    
    def test_wallet_balances_update_after_sell(self, auth_headers):
        """Test wallet balances update correctly after sell operation"""
        # Get initial balances
        initial_response = requests.get(
            f"{BASE_URL}/api/wallet/balances",
            headers=auth_headers
        )
        assert initial_response.status_code == 200
        initial_wallets = {w["asset"]: w["balance"] for w in initial_response.json().get("wallets", [])}
        initial_neno = initial_wallets.get("NENO", 0)
        initial_eur = initial_wallets.get("EUR", 0)
        
        # Execute sell
        sell_amount = 0.001
        sell_response = requests.post(
            f"{BASE_URL}/api/neno-exchange/sell",
            headers=auth_headers,
            json={"receive_asset": "EUR", "neno_amount": sell_amount}
        )
        assert sell_response.status_code == 200
        
        # Get updated balances
        updated_response = requests.get(
            f"{BASE_URL}/api/wallet/balances",
            headers=auth_headers
        )
        assert updated_response.status_code == 200
        updated_wallets = {w["asset"]: w["balance"] for w in updated_response.json().get("wallets", [])}
        updated_neno = updated_wallets.get("NENO", 0)
        updated_eur = updated_wallets.get("EUR", 0)
        
        # Verify NENO decreased
        assert updated_neno < initial_neno, f"NENO balance should decrease: {initial_neno} -> {updated_neno}"
        # Verify EUR increased
        assert updated_eur > initial_eur, f"EUR balance should increase: {initial_eur} -> {updated_eur}"
        
        print(f"BALANCE UPDATE (SELL): PASS - NENO: {initial_neno:.4f} -> {updated_neno:.4f}, EUR: {initial_eur:.2f} -> {updated_eur:.2f}")
    
    def test_transactions_show_settlement_hash(self, auth_headers):
        """Test GET /api/neno-exchange/transactions shows settlement_hash for each transaction"""
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/transactions",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Get transactions failed: {response.text}"
        data = response.json()
        
        assert "transactions" in data, "No transactions in response"
        transactions = data["transactions"]
        
        # Check that recent transactions have settlement_hash
        settlement_count = 0
        for tx in transactions[:10]:  # Check last 10 transactions
            if "settlement_hash" in tx and tx["settlement_hash"]:
                settlement_count += 1
                assert tx["settlement_hash"].startswith("0x"), f"Invalid settlement_hash format: {tx['settlement_hash']}"
        
        assert settlement_count > 0, "No transactions with settlement_hash found"
        print(f"TRANSACTIONS WITH SETTLEMENT: PASS - {settlement_count}/10 recent transactions have settlement_hash")


class TestE2EExchangeOperations:
    """E2E tests for the required exchange operations: Sell 10 NENO, Swap 10 NENO, Off-Ramp 10 NENO"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for admin user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get auth headers"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
    
    def test_e2e_sell_10_neno(self, auth_headers):
        """E2E Test: Sell 10 NENO with verified settlement hash"""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/sell",
            headers=auth_headers,
            json={"receive_asset": "EUR", "neno_amount": 10}
        )
        assert response.status_code == 200, f"Sell 10 NENO failed: {response.text}"
        data = response.json()
        
        tx = data["transaction"]
        assert tx["neno_amount"] == 10, "NENO amount should be 10"
        assert "settlement_hash" in tx, "No settlement_hash in transaction"
        assert tx["settlement_hash"].startswith("0x"), "Invalid settlement_hash format"
        assert tx.get("settlement_status") == "settled", "Transaction should be settled"
        
        print(f"E2E SELL 10 NENO: PASS")
        print(f"  - Settlement Hash: {tx['settlement_hash']}")
        print(f"  - EUR Received: {tx.get('receive_amount', 'N/A')}")
        print(f"  - Status: {tx.get('settlement_status')}")
    
    def test_e2e_swap_10_neno(self, auth_headers):
        """E2E Test: Swap 10 NENO with verified settlement hash"""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/swap",
            headers=auth_headers,
            json={"from_asset": "NENO", "to_asset": "ETH", "amount": 10}
        )
        assert response.status_code == 200, f"Swap 10 NENO failed: {response.text}"
        data = response.json()
        
        tx = data["transaction"]
        assert tx["from_amount"] == 10, "From amount should be 10"
        assert tx["from_asset"] == "NENO", "From asset should be NENO"
        assert "settlement_hash" in tx, "No settlement_hash in transaction"
        assert tx["settlement_hash"].startswith("0x"), "Invalid settlement_hash format"
        assert tx.get("settlement_status") == "settled", "Transaction should be settled"
        
        print(f"E2E SWAP 10 NENO: PASS")
        print(f"  - Settlement Hash: {tx['settlement_hash']}")
        print(f"  - ETH Received: {tx.get('to_amount', 'N/A')}")
        print(f"  - Status: {tx.get('settlement_status')}")
    
    def test_e2e_offramp_10_neno(self, auth_headers):
        """E2E Test: Off-Ramp 10 NENO with verified settlement hash"""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/offramp",
            headers=auth_headers,
            json={
                "neno_amount": 10,
                "destination": "bank",
                "destination_iban": "IT60X0542811101000000123456",
                "beneficiary_name": "Test User E2E"
            }
        )
        assert response.status_code == 200, f"Off-Ramp 10 NENO failed: {response.text}"
        data = response.json()
        
        tx = data["transaction"]
        assert tx["neno_amount"] == 10, "NENO amount should be 10"
        assert "settlement_hash" in tx, "No settlement_hash in transaction"
        assert tx["settlement_hash"].startswith("0x"), "Invalid settlement_hash format"
        assert tx.get("settlement_status") == "settled", "Transaction should be settled"
        
        print(f"E2E OFF-RAMP 10 NENO: PASS")
        print(f"  - Settlement Hash: {tx['settlement_hash']}")
        print(f"  - EUR Net: {tx.get('eur_net', 'N/A')}")
        print(f"  - Destination: {tx.get('destination_info', 'N/A')}")
        print(f"  - Status: {tx.get('settlement_status')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
