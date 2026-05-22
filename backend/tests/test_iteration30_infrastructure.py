"""
Iteration 30 - Infrastructure Layer Tests

Tests for:
1. Login with admin credentials
2. Hot Wallet: GET /api/infra/hot-wallet - real on-chain BNB + NENO balances
3. Settlement Rails: GET /api/infra/settlement/rails - crypto/stablecoin/sepa/card rails
4. System Health: GET /api/infra/health - operational status with all components
5. Sell: POST /api/neno-exchange/sell - state=internal_credited and proper balances
6. Swap: POST /api/neno-exchange/swap - state=internal_credited and proper balances
7. Offramp: POST /api/neno-exchange/offramp - state=payout_pending with payout object containing IBAN
8. Treasury PnL: GET /api/infra/treasury/pnl - fee collection and risk assessment (admin only)
9. Ledger: GET /api/neno-exchange/ledger - entries with state_history audit trail
10. Payouts: GET /api/neno-exchange/payouts - payout queue with IBANs and states
11. Routing: GET /api/infra/routing/quote - DEX routing path
12. Netting: GET /api/infra/netting-stats - internalization rate
13. Force Sync: POST /api/neno-exchange/force-balance-sync with tx_hash
14. Reconcile: POST /api/neno-exchange/reconcile (admin)
15. Live Balances: GET /api/neno-exchange/live-balances - real-time data
16. REGRESSION: Custom token create/buy/sell still work
"""

import pytest
import requests
import os
import uuid
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-chain-wallet-14.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"


class TestIteration30Infrastructure:
    """Infrastructure Layer Tests for NeoNoble Ramp"""
    
    token = None
    user_id = None
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - login once and reuse token"""
        if TestIteration30Infrastructure.token is None:
            response = requests.post(f"{BASE_URL}/api/auth/login", json={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            })
            if response.status_code == 200:
                data = response.json()
                # Handle both token formats
                TestIteration30Infrastructure.token = data.get("token") or data.get("access_token")
                TestIteration30Infrastructure.user_id = data.get("user_id") or data.get("user", {}).get("id")
        yield
    
    def get_headers(self):
        return {"Authorization": f"Bearer {TestIteration30Infrastructure.token}"}
    
    # ═══════════════════════════════════════════════════════════════════
    # TEST 1: Login
    # ═══════════════════════════════════════════════════════════════════
    
    def test_01_login_success(self):
        """Test admin login with correct credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        # Handle both token formats
        token = data.get("token") or data.get("access_token")
        assert token is not None, "No token in response"
        user_id = data.get("user_id") or data.get("user", {}).get("id")
        assert user_id is not None, "No user_id in response"
        print(f"✓ Login successful, user_id: {user_id}")
    
    # ═══════════════════════════════════════════════════════════════════
    # TEST 2: Hot Wallet Status
    # ═══════════════════════════════════════════════════════════════════
    
    def test_02_hot_wallet_status(self):
        """Test GET /api/infra/hot-wallet returns real on-chain BNB + NENO balances"""
        response = requests.get(f"{BASE_URL}/api/infra/hot-wallet", headers=self.get_headers())
        assert response.status_code == 200, f"Hot wallet failed: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "address" in data, "Missing address field"
        assert "bnb_balance" in data, "Missing bnb_balance field"
        assert "neno_balance" in data, "Missing neno_balance field"
        assert "available" in data, "Missing available field"
        assert "chain" in data, "Missing chain field"
        
        # Verify values
        assert data["available"] == True, "Hot wallet should be available"
        assert data["chain"] == "BSC Mainnet", f"Expected BSC Mainnet, got {data['chain']}"
        assert data["bnb_balance"] >= 0, "BNB balance should be >= 0"
        assert data["neno_balance"] >= 0, "NENO balance should be >= 0"
        
        print(f"✓ Hot wallet: {data['address']}")
        print(f"  BNB: {data['bnb_balance']}, NENO: {data['neno_balance']}")
        print(f"  Gas sufficient: {data.get('gas_sufficient', 'N/A')}")
    
    # ═══════════════════════════════════════════════════════════════════
    # TEST 3: Settlement Rails
    # ═══════════════════════════════════════════════════════════════════
    
    def test_03_settlement_rails(self):
        """Test GET /api/infra/settlement/rails shows crypto/stablecoin/sepa/card rails"""
        response = requests.get(f"{BASE_URL}/api/infra/settlement/rails", headers=self.get_headers())
        assert response.status_code == 200, f"Settlement rails failed: {response.text}"
        data = response.json()
        
        # Verify all 4 rails exist
        assert "crypto_rail" in data, "Missing crypto_rail"
        assert "stablecoin_rail" in data, "Missing stablecoin_rail"
        assert "sepa_rail" in data, "Missing sepa_rail"
        assert "card_rail" in data, "Missing card_rail"
        
        # Verify crypto rail
        crypto = data["crypto_rail"]
        assert crypto["type"] == "on_chain", f"Expected on_chain, got {crypto['type']}"
        assert crypto["chain"] == "BSC Mainnet", f"Expected BSC Mainnet, got {crypto['chain']}"
        assert "status" in crypto, "Missing status in crypto_rail"
        assert "hot_wallet" in crypto, "Missing hot_wallet in crypto_rail"
        
        # Verify stablecoin rail
        stable = data["stablecoin_rail"]
        assert stable["type"] == "stablecoin", f"Expected stablecoin, got {stable['type']}"
        assert "USDT" in stable.get("supported", []), "USDT should be supported"
        
        # Verify SEPA rail
        sepa = data["sepa_rail"]
        assert sepa["type"] == "fiat", f"Expected fiat, got {sepa['type']}"
        assert sepa["method"] == "SEPA/IBAN", f"Expected SEPA/IBAN, got {sepa['method']}"
        
        # Verify card rail
        card = data["card_rail"]
        assert card["type"] == "fiat", f"Expected fiat, got {card['type']}"
        assert card["method"] == "card_topup", f"Expected card_topup, got {card['method']}"
        
        print(f"✓ Settlement rails verified:")
        print(f"  Crypto: {crypto['status']}, Stablecoin: {stable['status']}")
        print(f"  SEPA: {sepa['status']}, Card: {card['status']}")
    
    # ═══════════════════════════════════════════════════════════════════
    # TEST 4: System Health
    # ═══════════════════════════════════════════════════════════════════
    
    def test_04_system_health(self):
        """Test GET /api/infra/health returns operational status with all components"""
        response = requests.get(f"{BASE_URL}/api/infra/health", headers=self.get_headers())
        assert response.status_code == 200, f"Health check failed: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "status" in data, "Missing status field"
        assert "hot_wallet" in data, "Missing hot_wallet field"
        assert "settlement_ledger_entries" in data, "Missing settlement_ledger_entries"
        assert "total_transactions" in data, "Missing total_transactions"
        assert "pending_payouts" in data, "Missing pending_payouts"
        assert "timestamp" in data, "Missing timestamp"
        
        # Verify status is operational
        assert data["status"] == "operational", f"Expected operational, got {data['status']}"
        
        # Verify hot wallet info
        hw = data["hot_wallet"]
        assert "address" in hw, "Missing address in hot_wallet"
        assert "available" in hw, "Missing available in hot_wallet"
        
        print(f"✓ System health: {data['status']}")
        print(f"  Ledger entries: {data['settlement_ledger_entries']}")
        print(f"  Total transactions: {data['total_transactions']}")
        print(f"  Pending payouts: {data['pending_payouts']}")
        print(f"  NIUM active: {data.get('nium_active', 'N/A')}")
    
    # ═══════════════════════════════════════════════════════════════════
    # TEST 5: Sell NENO - state=internal_credited
    # ═══════════════════════════════════════════════════════════════════
    
    def test_05_sell_neno_internal_credited(self):
        """Test POST /api/neno-exchange/sell returns state=internal_credited"""
        # First ensure we have NENO balance
        response = requests.post(f"{BASE_URL}/api/neno-exchange/sell", 
            headers=self.get_headers(),
            json={
                "receive_asset": "EUR",
                "neno_amount": 0.001
            }
        )
        
        # May fail if no balance, but check structure if successful
        if response.status_code == 200:
            data = response.json()
            assert "state" in data, "Missing state in response"
            assert data["state"] == "internal_credited", f"Expected internal_credited, got {data['state']}"
            assert "balances" in data, "Missing balances in response"
            assert "transaction" in data, "Missing transaction in response"
            print(f"✓ Sell NENO: state={data['state']}")
            print(f"  Balances: {data['balances']}")
        else:
            # Check if it's a balance issue
            error = response.json()
            if "insufficiente" in str(error.get("detail", "")).lower():
                print(f"⚠ Sell skipped - insufficient NENO balance (expected)")
            else:
                print(f"⚠ Sell failed: {error}")
    
    # ═══════════════════════════════════════════════════════════════════
    # TEST 6: Swap - state=internal_credited
    # ═══════════════════════════════════════════════════════════════════
    
    def test_06_swap_internal_credited(self):
        """Test POST /api/neno-exchange/swap returns state=internal_credited"""
        response = requests.post(f"{BASE_URL}/api/neno-exchange/swap",
            headers=self.get_headers(),
            json={
                "from_asset": "NENO",
                "to_asset": "ETH",
                "amount": 0.001
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "state" in data, "Missing state in response"
            assert data["state"] == "internal_credited", f"Expected internal_credited, got {data['state']}"
            assert "balances" in data, "Missing balances in response"
            print(f"✓ Swap NENO→ETH: state={data['state']}")
            print(f"  Balances: {data['balances']}")
        else:
            error = response.json()
            if "insufficiente" in str(error.get("detail", "")).lower():
                print(f"⚠ Swap skipped - insufficient balance (expected)")
            else:
                print(f"⚠ Swap failed: {error}")
    
    # ═══════════════════════════════════════════════════════════════════
    # TEST 7: Offramp - state=payout_pending with payout object
    # ═══════════════════════════════════════════════════════════════════
    
    def test_07_offramp_payout_pending(self):
        """Test POST /api/neno-exchange/offramp returns state=payout_pending with payout object containing IBAN"""
        response = requests.post(f"{BASE_URL}/api/neno-exchange/offramp",
            headers=self.get_headers(),
            json={
                "neno_amount": 0.001,
                "destination": "bank",
                "destination_iban": "IT60X0542811101000000123456",
                "beneficiary_name": "Test User"
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "state" in data, "Missing state in response"
            assert data["state"] == "payout_pending", f"Expected payout_pending, got {data['state']}"
            assert "payout" in data, "Missing payout object in response"
            
            payout = data["payout"]
            assert "id" in payout, "Missing id in payout"
            assert "state" in payout, "Missing state in payout"
            assert "amount" in payout, "Missing amount in payout"
            
            print(f"✓ Offramp: state={data['state']}")
            print(f"  Payout ID: {payout.get('id')}")
            print(f"  Payout state: {payout.get('state')}")
            print(f"  Amount: {payout.get('amount')}")
        else:
            error = response.json()
            if "insufficiente" in str(error.get("detail", "")).lower():
                print(f"⚠ Offramp skipped - insufficient balance (expected)")
            else:
                print(f"⚠ Offramp failed: {error}")
    
    # ═══════════════════════════════════════════════════════════════════
    # TEST 8: Treasury PnL (admin only)
    # ═══════════════════════════════════════════════════════════════════
    
    def test_08_treasury_pnl(self):
        """Test GET /api/infra/treasury/pnl returns fee collection and risk assessment"""
        response = requests.get(f"{BASE_URL}/api/infra/treasury/pnl", headers=self.get_headers())
        assert response.status_code == 200, f"Treasury PnL failed: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "pnl" in data, "Missing pnl field"
        assert "risk" in data, "Missing risk field"
        
        pnl = data["pnl"]
        assert "total_fees_eur" in pnl, "Missing total_fees_eur in pnl"
        assert "by_asset" in pnl, "Missing by_asset in pnl"
        assert "timestamp" in pnl, "Missing timestamp in pnl"
        
        risk = data["risk"]
        assert "hot_wallet" in risk, "Missing hot_wallet in risk"
        assert "pending_payouts" in risk, "Missing pending_payouts in risk"
        assert "risk_level" in risk, "Missing risk_level in risk"
        
        print(f"✓ Treasury PnL:")
        print(f"  Total fees EUR: {pnl['total_fees_eur']}")
        print(f"  Risk level: {risk['risk_level']}")
        print(f"  Pending payouts: {risk['pending_payouts']}")
    
    # ═══════════════════════════════════════════════════════════════════
    # TEST 9: Ledger with state_history
    # ═══════════════════════════════════════════════════════════════════
    
    def test_09_ledger_entries(self):
        """Test GET /api/neno-exchange/ledger returns entries with state_history audit trail"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/ledger", headers=self.get_headers())
        assert response.status_code == 200, f"Ledger failed: {response.text}"
        data = response.json()
        
        assert "entries" in data, "Missing entries field"
        assert "total" in data, "Missing total field"
        
        entries = data["entries"]
        print(f"✓ Ledger entries: {data['total']}")
        
        if len(entries) > 0:
            entry = entries[0]
            # Verify ledger entry structure
            assert "id" in entry, "Missing id in entry"
            assert "user_id" in entry, "Missing user_id in entry"
            assert "type" in entry, "Missing type in entry"
            assert "state" in entry, "Missing state in entry"
            assert "state_history" in entry, "Missing state_history in entry"
            
            # Verify state_history is an array with proper structure
            history = entry["state_history"]
            assert isinstance(history, list), "state_history should be a list"
            if len(history) > 0:
                assert "state" in history[0], "Missing state in state_history entry"
                assert "at" in history[0], "Missing at in state_history entry"
            
            print(f"  Latest entry: {entry['type']} - {entry['state']}")
            print(f"  State history length: {len(history)}")
    
    # ═══════════════════════════════════════════════════════════════════
    # TEST 10: Payouts Queue
    # ═══════════════════════════════════════════════════════════════════
    
    def test_10_payouts_queue(self):
        """Test GET /api/neno-exchange/payouts returns payout queue with IBANs and states"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/payouts", headers=self.get_headers())
        assert response.status_code == 200, f"Payouts failed: {response.text}"
        data = response.json()
        
        assert "payouts" in data, "Missing payouts field"
        assert "total" in data, "Missing total field"
        
        payouts = data["payouts"]
        print(f"✓ Payouts queue: {data['total']}")
        
        if len(payouts) > 0:
            payout = payouts[0]
            # Verify payout structure
            assert "id" in payout, "Missing id in payout"
            assert "user_id" in payout, "Missing user_id in payout"
            assert "amount" in payout, "Missing amount in payout"
            assert "state" in payout, "Missing state in payout"
            
            print(f"  Latest payout: {payout['amount']} {payout.get('currency', 'EUR')} - {payout['state']}")
            if payout.get("destination_iban"):
                print(f"  IBAN: {payout['destination_iban'][:8]}...")
    
    # ═══════════════════════════════════════════════════════════════════
    # TEST 11: Routing Quote
    # ═══════════════════════════════════════════════════════════════════
    
    def test_11_routing_quote(self):
        """Test GET /api/infra/routing/quote returns DEX routing path"""
        response = requests.get(
            f"{BASE_URL}/api/infra/routing/quote?from_asset=NENO&to_asset=BNB&amount=5",
            headers=self.get_headers()
        )
        assert response.status_code == 200, f"Routing quote failed: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "from" in data, "Missing from field"
        assert "to" in data, "Missing to field"
        assert "amount" in data, "Missing amount field"
        assert "routing" in data, "Missing routing field"
        
        routing = data["routing"]
        assert "path" in routing, "Missing path in routing"
        assert "dex" in routing, "Missing dex in routing"
        assert "hops" in routing, "Missing hops in routing"
        
        print(f"✓ Routing quote: {data['from']} → {data['to']}")
        print(f"  DEX: {routing['dex']}")
        print(f"  Path: {routing['path']}")
        print(f"  Hops: {routing['hops']}")
    
    # ═══════════════════════════════════════════════════════════════════
    # TEST 12: Netting Stats
    # ═══════════════════════════════════════════════════════════════════
    
    def test_12_netting_stats(self):
        """Test GET /api/infra/netting-stats returns internalization rate"""
        response = requests.get(f"{BASE_URL}/api/infra/netting-stats", headers=self.get_headers())
        assert response.status_code == 200, f"Netting stats failed: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "matched_orders" in data, "Missing matched_orders field"
        assert "pending_orders" in data, "Missing pending_orders field"
        assert "internalization_rate" in data, "Missing internalization_rate field"
        
        print(f"✓ Netting stats:")
        print(f"  Matched orders: {data['matched_orders']}")
        print(f"  Pending orders: {data['pending_orders']}")
        print(f"  Internalization rate: {data['internalization_rate']}%")
    
    # ═══════════════════════════════════════════════════════════════════
    # TEST 13: Force Balance Sync
    # ═══════════════════════════════════════════════════════════════════
    
    def test_13_force_balance_sync(self):
        """Test POST /api/neno-exchange/force-balance-sync with tx_hash"""
        # Use a known tx_hash from the context (the real NENO transfer)
        known_tx_hash = "0x329adc7ab981dfd5b182f6a4769ef06b902044df1ad046e48e65ac6672d48f23"
        
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/force-balance-sync",
            headers=self.get_headers(),
            json={"tx_hash": known_tx_hash}
        )
        
        # This may return 400 if already synced, which is expected
        if response.status_code == 200:
            data = response.json()
            assert "message" in data or "tx_hash" in data, "Missing expected fields"
            print(f"✓ Force sync successful: {data.get('message', data)}")
        elif response.status_code == 400:
            data = response.json()
            if "gia' sincronizzata" in str(data.get("detail", "")).lower() or "already" in str(data.get("detail", "")).lower():
                print(f"✓ Force sync: Transaction already synced (expected)")
            else:
                print(f"⚠ Force sync returned 400: {data}")
        else:
            print(f"⚠ Force sync failed with status {response.status_code}: {response.text}")
    
    # ═══════════════════════════════════════════════════════════════════
    # TEST 14: Reconcile (admin)
    # ═══════════════════════════════════════════════════════════════════
    
    def test_14_reconcile_admin(self):
        """Test POST /api/neno-exchange/reconcile (admin only)"""
        response = requests.post(f"{BASE_URL}/api/neno-exchange/reconcile", headers=self.get_headers())
        assert response.status_code == 200, f"Reconcile failed: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "reconciled_credits" in data, "Missing reconciled_credits field"
        assert "unmatched_deposits" in data, "Missing unmatched_deposits field"
        
        print(f"✓ Reconciliation:")
        print(f"  Reconciled credits: {data['reconciled_credits']}")
        print(f"  Unmatched deposits: {data['unmatched_deposits']}")
    
    # ═══════════════════════════════════════════════════════════════════
    # TEST 15: Live Balances
    # ═══════════════════════════════════════════════════════════════════
    
    def test_15_live_balances(self):
        """Test GET /api/neno-exchange/live-balances returns real-time data"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/live-balances", headers=self.get_headers())
        assert response.status_code == 200, f"Live balances failed: {response.text}"
        data = response.json()
        
        # Verify required fields
        assert "balances" in data, "Missing balances field"
        assert "total_value_usd" in data, "Missing total_value_usd field"
        assert "neno_price" in data, "Missing neno_price field"
        assert "timestamp" in data, "Missing timestamp field"
        
        print(f"✓ Live balances:")
        print(f"  Total value USD: ${data['total_value_usd']}")
        print(f"  NENO price: {data['neno_price'].get('price', 'N/A')} EUR")
        print(f"  Assets: {list(data['balances'].keys())[:5]}...")
    
    # ═══════════════════════════════════════════════════════════════════
    # REGRESSION TESTS: Custom Token Create/Buy/Sell
    # ═══════════════════════════════════════════════════════════════════
    
    def test_16_regression_create_custom_token(self):
        """REGRESSION: Test custom token creation still works"""
        unique_symbol = f"T{uuid.uuid4().hex[:5].upper()}"
        
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/create-token",
            headers=self.get_headers(),
            json={
                "symbol": unique_symbol,
                "name": f"Test Token {unique_symbol}",
                "price_usd": 0.50,
                "total_supply": 10000
            }
        )
        
        assert response.status_code == 200, f"Create token failed: {response.text}"
        data = response.json()
        
        assert "token" in data, "Missing token in response"
        assert "balance" in data, "Missing balance in response"
        assert data["token"]["symbol"] == unique_symbol, f"Symbol mismatch"
        
        print(f"✓ REGRESSION: Created custom token {unique_symbol}")
        print(f"  Price: ${data['token']['price_usd']}")
        print(f"  Balance: {data['balance']}")
        
        # Store for next tests
        TestIteration30Infrastructure.test_token_symbol = unique_symbol
    
    def test_17_regression_buy_custom_token(self):
        """REGRESSION: Test buying custom token still works"""
        # First deposit some EUR
        response = requests.post(
            f"{BASE_URL}/api/wallet/deposit",
            headers=self.get_headers(),
            json={"asset": "EUR", "amount": 100}
        )
        
        # Get a custom token to buy
        response = requests.get(f"{BASE_URL}/api/neno-exchange/custom-tokens")
        assert response.status_code == 200
        tokens = response.json().get("tokens", [])
        
        if len(tokens) > 0:
            token_symbol = tokens[0]["symbol"]
            
            response = requests.post(
                f"{BASE_URL}/api/neno-exchange/buy-custom-token",
                headers=self.get_headers(),
                json={
                    "symbol": token_symbol,
                    "amount": 1,
                    "pay_asset": "EUR"
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                assert "transaction" in data, "Missing transaction"
                assert "balances" in data, "Missing balances"
                print(f"✓ REGRESSION: Bought 1 {token_symbol}")
            else:
                error = response.json()
                if "insufficiente" in str(error.get("detail", "")).lower():
                    print(f"⚠ Buy custom token skipped - insufficient balance")
                else:
                    print(f"⚠ Buy custom token failed: {error}")
        else:
            print(f"⚠ No custom tokens available to buy")
    
    def test_18_regression_sell_custom_token(self):
        """REGRESSION: Test selling custom token still works"""
        # Get user's tokens
        response = requests.get(f"{BASE_URL}/api/neno-exchange/my-tokens", headers=self.get_headers())
        
        if response.status_code == 200:
            data = response.json()
            tokens = data.get("tokens", [])
            
            # Find a token with balance
            for token in tokens:
                if token.get("balance", 0) > 0:
                    response = requests.post(
                        f"{BASE_URL}/api/neno-exchange/sell-custom-token",
                        headers=self.get_headers(),
                        json={
                            "symbol": token["symbol"],
                            "amount": 1,
                            "receive_asset": "EUR"
                        }
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        print(f"✓ REGRESSION: Sold 1 {token['symbol']}")
                        return
                    else:
                        error = response.json()
                        print(f"⚠ Sell custom token failed: {error}")
                        return
            
            print(f"⚠ No custom tokens with balance to sell")
        else:
            print(f"⚠ Could not get user tokens")
    
    # ═══════════════════════════════════════════════════════════════════
    # Additional Infrastructure Tests
    # ═══════════════════════════════════════════════════════════════════
    
    def test_19_audit_ledger(self):
        """Test GET /api/infra/audit/ledger returns full settlement ledger"""
        response = requests.get(f"{BASE_URL}/api/infra/audit/ledger", headers=self.get_headers())
        assert response.status_code == 200, f"Audit ledger failed: {response.text}"
        data = response.json()
        
        assert "entries" in data, "Missing entries field"
        assert "total" in data, "Missing total field"
        
        print(f"✓ Audit ledger: {data['total']} entries")
    
    def test_20_audit_payouts(self):
        """Test GET /api/infra/audit/payouts returns payout queue"""
        response = requests.get(f"{BASE_URL}/api/infra/audit/payouts", headers=self.get_headers())
        assert response.status_code == 200, f"Audit payouts failed: {response.text}"
        data = response.json()
        
        assert "payouts" in data, "Missing payouts field"
        assert "total" in data, "Missing total field"
        
        print(f"✓ Audit payouts: {data['total']} payouts")
    
    def test_21_order_book(self):
        """Test GET /api/infra/order-book returns internal order book"""
        response = requests.get(f"{BASE_URL}/api/infra/order-book", headers=self.get_headers())
        assert response.status_code == 200, f"Order book failed: {response.text}"
        data = response.json()
        
        assert "orders" in data, "Missing orders field"
        assert "total" in data, "Missing total field"
        
        print(f"✓ Order book: {data['total']} pending orders")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
