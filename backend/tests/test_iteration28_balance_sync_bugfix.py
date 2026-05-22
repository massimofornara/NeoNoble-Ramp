"""
Iteration 28 - Balance Sync Bug Fix Tests

CRITICAL BUG FIX: On-chain transactions (sell, swap, offramp) were executing successfully 
on BSC mainnet but internal wallet balances were not updating.

Root cause: verify-deposit endpoint credited NENO to internal wallet, but sell/swap/offramp 
endpoints skipped the NENO debit when tx_hash was present.

Fix: removed the 'if not onchain_tx' guard around debit operations so NENO is always debited.

Test Flow:
1. Login as admin
2. Get initial NENO/EUR balances
3. Deposit NENO to have balance
4. Sell NENO - verify NENO decreases, EUR increases
5. Swap NENO → ETH - verify NENO decreases, ETH increases
6. Offramp NENO - verify NENO decreases
7. Test insufficient balance errors
8. Regression tests for buy, create-token, live-balances
"""

import pytest
import requests
import os
import time
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestBalanceSyncBugFix:
    """Tests for the critical balance sync bug fix in sell/swap/offramp endpoints"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@neonobleramp.com",
            "password": "Admin1234!"
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        yield
        
        self.session.close()
    
    def get_balance(self, asset: str) -> float:
        """Helper to get current balance for an asset"""
        resp = self.session.get(f"{BASE_URL}/api/wallet/balances")
        if resp.status_code != 200:
            return 0.0
        wallets = resp.json().get("wallets", [])
        for w in wallets:
            if w.get("asset") == asset:
                return w.get("balance", 0.0)
        return 0.0
    
    def deposit_neno(self, amount: float) -> dict:
        """Helper to deposit NENO for testing"""
        resp = self.session.post(f"{BASE_URL}/api/wallet/deposit", json={
            "asset": "NENO",
            "amount": amount
        })
        return resp.json() if resp.status_code == 200 else {}
    
    def deposit_eur(self, amount: float) -> dict:
        """Helper to deposit EUR for testing"""
        resp = self.session.post(f"{BASE_URL}/api/wallet/deposit", json={
            "asset": "EUR",
            "amount": amount
        })
        return resp.json() if resp.status_code == 200 else {}

    # ============ BUG FIX TESTS: SELL ============
    
    def test_sell_neno_debits_balance(self):
        """BUG FIX: POST /api/neno-exchange/sell should DEBIT NENO and CREDIT receive_asset"""
        # Deposit NENO first
        self.deposit_neno(50)
        time.sleep(0.3)
        
        initial_neno = self.get_balance("NENO")
        initial_eur = self.get_balance("EUR")
        
        assert initial_neno >= 10, f"Need at least 10 NENO to test, have {initial_neno}"
        
        # Sell 10 NENO for EUR
        sell_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/sell", json={
            "receive_asset": "EUR",
            "neno_amount": 10
        })
        
        assert sell_resp.status_code == 200, f"Sell failed: {sell_resp.text}"
        sell_data = sell_resp.json()
        
        # Verify response contains balances
        assert "balances" in sell_data, "Response should contain balances"
        assert "NENO" in sell_data["balances"], "Response should contain NENO balance"
        assert "EUR" in sell_data["balances"], "Response should contain EUR balance"
        
        # Verify NENO was debited (balance decreased)
        new_neno = sell_data["balances"]["NENO"]
        assert new_neno < initial_neno, f"NENO should decrease: was {initial_neno}, now {new_neno}"
        assert abs(new_neno - (initial_neno - 10)) < 0.001, f"NENO should decrease by 10: expected {initial_neno - 10}, got {new_neno}"
        
        # Verify EUR was credited (balance increased)
        new_eur = sell_data["balances"]["EUR"]
        assert new_eur > initial_eur, f"EUR should increase: was {initial_eur}, now {new_eur}"
        
        # Verify transaction record
        tx = sell_data.get("transaction", {})
        assert tx.get("type") == "sell_neno"
        assert tx.get("neno_amount") == 10
        assert tx.get("status") == "completed"
        
        print(f"SELL TEST PASSED: NENO {initial_neno} -> {new_neno}, EUR {initial_eur} -> {new_eur}")
    
    def test_sell_insufficient_balance_returns_400(self):
        """BUG FIX: Sell with insufficient NENO balance should return 400 error"""
        # Get current balance
        current_neno = self.get_balance("NENO")
        
        # Try to sell more than available
        sell_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/sell", json={
            "receive_asset": "EUR",
            "neno_amount": current_neno + 1000000  # Way more than available
        })
        
        assert sell_resp.status_code == 400, f"Expected 400, got {sell_resp.status_code}"
        error_data = sell_resp.json()
        assert "insufficiente" in error_data.get("detail", "").lower(), f"Expected insufficient balance error: {error_data}"
        
        print(f"SELL INSUFFICIENT BALANCE TEST PASSED: Got 400 with message '{error_data.get('detail')}'")

    # ============ BUG FIX TESTS: SWAP ============
    
    def test_swap_neno_debits_from_asset(self):
        """BUG FIX: POST /api/neno-exchange/swap with from_asset=NENO should DEBIT NENO"""
        # Deposit NENO first
        self.deposit_neno(50)
        time.sleep(0.3)
        
        initial_neno = self.get_balance("NENO")
        initial_eth = self.get_balance("ETH")
        
        assert initial_neno >= 5, f"Need at least 5 NENO to test, have {initial_neno}"
        
        # Swap 5 NENO → ETH
        swap_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/swap", json={
            "from_asset": "NENO",
            "to_asset": "ETH",
            "amount": 5
        })
        
        assert swap_resp.status_code == 200, f"Swap failed: {swap_resp.text}"
        swap_data = swap_resp.json()
        
        # Verify response contains balances
        assert "balances" in swap_data, "Response should contain balances"
        assert "NENO" in swap_data["balances"], "Response should contain NENO balance"
        assert "ETH" in swap_data["balances"], "Response should contain ETH balance"
        
        # Verify NENO was debited (balance decreased)
        new_neno = swap_data["balances"]["NENO"]
        assert new_neno < initial_neno, f"NENO should decrease: was {initial_neno}, now {new_neno}"
        assert abs(new_neno - (initial_neno - 5)) < 0.001, f"NENO should decrease by 5: expected {initial_neno - 5}, got {new_neno}"
        
        # Verify ETH was credited (balance increased)
        new_eth = swap_data["balances"]["ETH"]
        assert new_eth > initial_eth, f"ETH should increase: was {initial_eth}, now {new_eth}"
        
        # Verify transaction record
        tx = swap_data.get("transaction", {})
        assert tx.get("type") == "swap"
        assert tx.get("from_asset") == "NENO"
        assert tx.get("to_asset") == "ETH"
        assert tx.get("from_amount") == 5
        assert tx.get("status") == "completed"
        
        print(f"SWAP TEST PASSED: NENO {initial_neno} -> {new_neno}, ETH {initial_eth} -> {new_eth}")
    
    def test_swap_insufficient_balance_returns_400(self):
        """BUG FIX: Swap with insufficient from_asset balance should return 400 error"""
        # Get current balance
        current_neno = self.get_balance("NENO")
        
        # Try to swap more than available
        swap_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/swap", json={
            "from_asset": "NENO",
            "to_asset": "ETH",
            "amount": current_neno + 1000000  # Way more than available
        })
        
        assert swap_resp.status_code == 400, f"Expected 400, got {swap_resp.status_code}"
        error_data = swap_resp.json()
        assert "insufficiente" in error_data.get("detail", "").lower(), f"Expected insufficient balance error: {error_data}"
        
        print(f"SWAP INSUFFICIENT BALANCE TEST PASSED: Got 400 with message '{error_data.get('detail')}'")

    # ============ BUG FIX TESTS: OFFRAMP ============
    
    def test_offramp_debits_neno_balance(self):
        """BUG FIX: POST /api/neno-exchange/offramp should DEBIT NENO from internal balance"""
        # Deposit NENO first
        self.deposit_neno(50)
        time.sleep(0.3)
        
        initial_neno = self.get_balance("NENO")
        
        assert initial_neno >= 3, f"Need at least 3 NENO to test, have {initial_neno}"
        
        # Offramp 3 NENO to bank
        offramp_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/offramp", json={
            "neno_amount": 3,
            "destination": "bank",
            "destination_iban": "IT80V1810301600068254758246",
            "beneficiary_name": "Test User"
        })
        
        assert offramp_resp.status_code == 200, f"Offramp failed: {offramp_resp.text}"
        offramp_data = offramp_resp.json()
        
        # Verify response contains neno_balance
        assert "neno_balance" in offramp_data, "Response should contain neno_balance"
        
        # Verify NENO was debited (balance decreased)
        new_neno = offramp_data["neno_balance"]
        assert new_neno < initial_neno, f"NENO should decrease: was {initial_neno}, now {new_neno}"
        assert abs(new_neno - (initial_neno - 3)) < 0.001, f"NENO should decrease by 3: expected {initial_neno - 3}, got {new_neno}"
        
        # Verify transaction record
        tx = offramp_data.get("transaction", {})
        assert tx.get("type") == "neno_offramp"
        assert tx.get("neno_amount") == 3
        assert tx.get("destination") == "bank"
        
        print(f"OFFRAMP TEST PASSED: NENO {initial_neno} -> {new_neno}")
    
    def test_offramp_insufficient_balance_returns_400(self):
        """BUG FIX: Offramp with insufficient NENO balance should return 400 error"""
        # Get current balance
        current_neno = self.get_balance("NENO")
        
        # Try to offramp more than available
        offramp_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/offramp", json={
            "neno_amount": current_neno + 1000000,  # Way more than available
            "destination": "bank",
            "destination_iban": "IT80V1810301600068254758246",
            "beneficiary_name": "Test User"
        })
        
        assert offramp_resp.status_code == 400, f"Expected 400, got {offramp_resp.status_code}"
        error_data = offramp_resp.json()
        assert "insufficiente" in error_data.get("detail", "").lower(), f"Expected insufficient balance error: {error_data}"
        
        print(f"OFFRAMP INSUFFICIENT BALANCE TEST PASSED: Got 400 with message '{error_data.get('detail')}'")

    # ============ REGRESSION TESTS ============
    
    def test_buy_neno_still_works(self):
        """REGRESSION: POST /api/neno-exchange/buy should still work (buy NENO with EUR)"""
        # Deposit EUR first
        self.deposit_eur(200000)  # 200k EUR to buy NENO
        time.sleep(0.3)
        
        initial_neno = self.get_balance("NENO")
        initial_eur = self.get_balance("EUR")
        
        # Buy 1 NENO with EUR
        buy_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/buy", json={
            "pay_asset": "EUR",
            "neno_amount": 1
        })
        
        assert buy_resp.status_code == 200, f"Buy failed: {buy_resp.text}"
        buy_data = buy_resp.json()
        
        # Verify NENO increased
        new_neno = buy_data["balances"]["NENO"]
        assert new_neno > initial_neno, f"NENO should increase: was {initial_neno}, now {new_neno}"
        
        # Verify EUR decreased
        new_eur = buy_data["balances"]["EUR"]
        assert new_eur < initial_eur, f"EUR should decrease: was {initial_eur}, now {new_eur}"
        
        print(f"BUY REGRESSION TEST PASSED: NENO {initial_neno} -> {new_neno}, EUR {initial_eur} -> {new_eur}")
    
    def test_create_token_still_works(self):
        """REGRESSION: POST /api/neno-exchange/create-token should still work"""
        unique_symbol = f"T{uuid.uuid4().hex[:5].upper()}"
        
        create_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/create-token", json={
            "symbol": unique_symbol,
            "name": f"Test Token {unique_symbol}",
            "price_usd": 0.50,
            "total_supply": 1000
        })
        
        assert create_resp.status_code == 200, f"Create token failed: {create_resp.text}"
        create_data = create_resp.json()
        
        assert "token" in create_data
        assert create_data["token"]["symbol"] == unique_symbol
        assert create_data["balance"] == 1000
        
        print(f"CREATE TOKEN REGRESSION TEST PASSED: Created {unique_symbol}")
    
    def test_live_balances_returns_updated_data(self):
        """REGRESSION: GET /api/neno-exchange/live-balances should return up-to-date balances"""
        resp = self.session.get(f"{BASE_URL}/api/neno-exchange/live-balances")
        
        assert resp.status_code == 200, f"Live balances failed: {resp.text}"
        data = resp.json()
        
        assert "balances" in data
        assert "total_value_usd" in data
        assert "neno_price" in data
        assert "timestamp" in data
        
        # Verify structure of balance entries
        for asset, info in data["balances"].items():
            assert "balance" in info
            assert "price_usd" in info
            assert "value_usd" in info
            assert "is_custom" in info
        
        print(f"LIVE BALANCES REGRESSION TEST PASSED: {len(data['balances'])} assets, total ${data['total_value_usd']}")
    
    def test_buy_custom_token_still_works(self):
        """REGRESSION: POST /api/neno-exchange/buy-custom-token should still work"""
        # First create a token
        unique_symbol = f"B{uuid.uuid4().hex[:5].upper()}"
        
        create_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/create-token", json={
            "symbol": unique_symbol,
            "name": f"Buy Test Token {unique_symbol}",
            "price_usd": 1.00,
            "total_supply": 10000
        })
        assert create_resp.status_code == 200
        
        # Deposit EUR
        self.deposit_eur(100)
        time.sleep(0.3)
        
        initial_token = self.get_balance(unique_symbol)
        
        # Buy some of the token
        buy_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/buy-custom-token", json={
            "symbol": unique_symbol,
            "amount": 10,
            "pay_asset": "EUR"
        })
        
        assert buy_resp.status_code == 200, f"Buy custom token failed: {buy_resp.text}"
        buy_data = buy_resp.json()
        
        new_token = buy_data["balances"][unique_symbol]
        assert new_token > initial_token, f"Token balance should increase"
        
        print(f"BUY CUSTOM TOKEN REGRESSION TEST PASSED: {unique_symbol} {initial_token} -> {new_token}")
    
    def test_sell_custom_token_still_works(self):
        """REGRESSION: POST /api/neno-exchange/sell-custom-token should still work"""
        # First create a token
        unique_symbol = f"S{uuid.uuid4().hex[:5].upper()}"
        
        create_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/create-token", json={
            "symbol": unique_symbol,
            "name": f"Sell Test Token {unique_symbol}",
            "price_usd": 1.00,
            "total_supply": 10000
        })
        assert create_resp.status_code == 200
        
        initial_token = self.get_balance(unique_symbol)
        initial_eur = self.get_balance("EUR")
        
        # Sell some of the token
        sell_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/sell-custom-token", json={
            "symbol": unique_symbol,
            "amount": 100,
            "receive_asset": "EUR"
        })
        
        assert sell_resp.status_code == 200, f"Sell custom token failed: {sell_resp.text}"
        sell_data = sell_resp.json()
        
        new_token = sell_data["balances"][unique_symbol]
        new_eur = sell_data["balances"]["EUR"]
        
        assert new_token < initial_token, f"Token balance should decrease"
        assert new_eur > initial_eur, f"EUR balance should increase"
        
        print(f"SELL CUSTOM TOKEN REGRESSION TEST PASSED: {unique_symbol} {initial_token} -> {new_token}, EUR {initial_eur} -> {new_eur}")


class TestBalanceVerification:
    """Additional tests to verify balance persistence after operations"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Login and get auth token"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@neonobleramp.com",
            "password": "Admin1234!"
        })
        assert login_resp.status_code == 200
        self.token = login_resp.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        
        yield
        self.session.close()
    
    def get_balance(self, asset: str) -> float:
        resp = self.session.get(f"{BASE_URL}/api/wallet/balances")
        if resp.status_code != 200:
            return 0.0
        wallets = resp.json().get("wallets", [])
        for w in wallets:
            if w.get("asset") == asset:
                return w.get("balance", 0.0)
        return 0.0
    
    def test_sell_balance_persists_after_refetch(self):
        """Verify that after sell, the balance change persists when refetched"""
        # Deposit NENO
        self.session.post(f"{BASE_URL}/api/wallet/deposit", json={"asset": "NENO", "amount": 20})
        time.sleep(0.3)
        
        initial_neno = self.get_balance("NENO")
        
        # Sell 5 NENO
        sell_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/sell", json={
            "receive_asset": "EUR",
            "neno_amount": 5
        })
        assert sell_resp.status_code == 200
        
        # Wait a moment and refetch balance
        time.sleep(0.5)
        refetched_neno = self.get_balance("NENO")
        
        # Verify the balance change persisted
        expected_neno = initial_neno - 5
        assert abs(refetched_neno - expected_neno) < 0.001, f"Balance should persist: expected {expected_neno}, got {refetched_neno}"
        
        print(f"BALANCE PERSISTENCE TEST PASSED: Initial {initial_neno}, After sell {refetched_neno}")
    
    def test_swap_balance_persists_after_refetch(self):
        """Verify that after swap, the balance change persists when refetched"""
        # Deposit NENO
        self.session.post(f"{BASE_URL}/api/wallet/deposit", json={"asset": "NENO", "amount": 20})
        time.sleep(0.3)
        
        initial_neno = self.get_balance("NENO")
        initial_eth = self.get_balance("ETH")
        
        # Swap 3 NENO → ETH
        swap_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/swap", json={
            "from_asset": "NENO",
            "to_asset": "ETH",
            "amount": 3
        })
        assert swap_resp.status_code == 200
        
        # Wait a moment and refetch balances
        time.sleep(0.5)
        refetched_neno = self.get_balance("NENO")
        refetched_eth = self.get_balance("ETH")
        
        # Verify the balance changes persisted
        expected_neno = initial_neno - 3
        assert abs(refetched_neno - expected_neno) < 0.001, f"NENO balance should persist: expected {expected_neno}, got {refetched_neno}"
        assert refetched_eth > initial_eth, f"ETH balance should increase: was {initial_eth}, now {refetched_eth}"
        
        print(f"SWAP BALANCE PERSISTENCE TEST PASSED: NENO {initial_neno} -> {refetched_neno}, ETH {initial_eth} -> {refetched_eth}")
    
    def test_offramp_balance_persists_after_refetch(self):
        """Verify that after offramp, the balance change persists when refetched"""
        # Deposit NENO
        self.session.post(f"{BASE_URL}/api/wallet/deposit", json={"asset": "NENO", "amount": 20})
        time.sleep(0.3)
        
        initial_neno = self.get_balance("NENO")
        
        # Offramp 2 NENO
        offramp_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/offramp", json={
            "neno_amount": 2,
            "destination": "bank",
            "destination_iban": "IT80V1810301600068254758246",
            "beneficiary_name": "Test User"
        })
        assert offramp_resp.status_code == 200
        
        # Wait a moment and refetch balance
        time.sleep(0.5)
        refetched_neno = self.get_balance("NENO")
        
        # Verify the balance change persisted
        expected_neno = initial_neno - 2
        assert abs(refetched_neno - expected_neno) < 0.001, f"Balance should persist: expected {expected_neno}, got {refetched_neno}"
        
        print(f"OFFRAMP BALANCE PERSISTENCE TEST PASSED: Initial {initial_neno}, After offramp {refetched_neno}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
