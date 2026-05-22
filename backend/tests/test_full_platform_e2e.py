"""
Full Platform E2E Test - NeoNoble Ramp
Tests all endpoints across all phases:
- Auth & User Management
- Trading Engine (Market, Limit, Stop-Loss, Take-Profit orders)
- Card Management (NIUM API)
- Wallet & Settlement
- Multi-Chain Wallet
- Banking Rails (IBAN/SEPA)
- Paper Trading
- Margin Trading
- WebSocket Infrastructure
- Token & Subscriptions
- Market Data
- Admin Analytics
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-chain-wallet-14.preview.emergentagent.com').rstrip('/')

# Test credentials
REGULAR_USER = {"email": "testchart@example.com", "password": "Test1234!"}
ADMIN_USER = {"email": "admin@neonobleramp.com", "password": "Admin1234!"}


class TestAuth:
    """Authentication endpoint tests"""
    
    def test_01_health_check(self):
        """Test health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print("PASS: Health check")
    
    def test_02_regular_user_login(self):
        """Test regular user login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=REGULAR_USER)
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["email"] == REGULAR_USER["email"]
        assert data["user"]["role"] == "USER"
        print(f"PASS: Regular user login - {data['user']['email']}")
    
    def test_03_admin_user_login(self):
        """Test admin user login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_USER)
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["email"] == ADMIN_USER["email"]
        assert data["user"]["role"] == "ADMIN"
        print(f"PASS: Admin user login - {data['user']['email']}")
    
    def test_04_get_current_user(self, auth_token):
        """Test GET /api/auth/me"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "email" in data
        print(f"PASS: GET /api/auth/me - {data['email']}")


class TestTradingEngine:
    """Trading Engine tests - pairs, orders, order book, candles"""
    
    def test_05_get_trading_pairs(self):
        """Test GET /api/trading/pairs returns 15 pairs including NENO"""
        response = requests.get(f"{BASE_URL}/api/trading/pairs")
        assert response.status_code == 200
        data = response.json()
        assert "pairs" in data
        assert len(data["pairs"]) >= 15
        pair_ids = [p["id"] for p in data["pairs"]]
        assert "NENO-EUR" in pair_ids
        assert "NENO-USDT" in pair_ids
        assert "BTC-EUR" in pair_ids
        print(f"PASS: GET /api/trading/pairs - {len(data['pairs'])} pairs")
    
    def test_06_get_btc_eur_ticker(self):
        """Test GET /api/trading/pairs/BTC-EUR/ticker"""
        response = requests.get(f"{BASE_URL}/api/trading/pairs/BTC-EUR/ticker")
        assert response.status_code == 200
        data = response.json()
        assert "last_price" in data
        assert "best_bid" in data
        assert "best_ask" in data
        print(f"PASS: BTC-EUR ticker - last_price: {data['last_price']}")
    
    def test_07_get_neno_eur_ticker(self):
        """Test GET /api/trading/pairs/NENO-EUR/ticker"""
        response = requests.get(f"{BASE_URL}/api/trading/pairs/NENO-EUR/ticker")
        assert response.status_code == 200
        data = response.json()
        assert "last_price" in data
        print(f"PASS: NENO-EUR ticker - last_price: {data['last_price']}")
    
    def test_08_get_orderbook(self):
        """Test GET /api/trading/pairs/BTC-EUR/orderbook"""
        response = requests.get(f"{BASE_URL}/api/trading/pairs/BTC-EUR/orderbook")
        assert response.status_code == 200
        data = response.json()
        assert "bids" in data
        assert "asks" in data
        print(f"PASS: BTC-EUR orderbook - {len(data['bids'])} bids, {len(data['asks'])} asks")
    
    def test_09_get_candles(self):
        """Test GET /api/trading/pairs/BTC-EUR/candles"""
        response = requests.get(f"{BASE_URL}/api/trading/pairs/BTC-EUR/candles?interval=1h")
        assert response.status_code == 200
        data = response.json()
        assert "candles" in data
        assert len(data["candles"]) > 0
        candle = data["candles"][0]
        assert "open" in candle
        assert "high" in candle
        assert "low" in candle
        assert "close" in candle
        print(f"PASS: BTC-EUR candles - {len(data['candles'])} candles")
    
    def test_10_market_buy_order(self, auth_token):
        """Test POST /api/trading/orders - market buy BTC-EUR"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {
            "pair_id": "BTC-EUR",
            "side": "buy",
            "order_type": "market",
            "quantity": 0.01
        }
        response = requests.post(f"{BASE_URL}/api/trading/orders", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "order" in data
        assert data["order"]["status"] in ["filled", "partially_filled", "open"]
        print(f"PASS: Market buy order - status: {data['order']['status']}")
    
    def test_11_limit_sell_order(self, auth_token):
        """Test POST /api/trading/orders - limit sell NENO-EUR"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {
            "pair_id": "NENO-EUR",
            "side": "sell",
            "order_type": "limit",
            "quantity": 50,
            "price": 0.55
        }
        response = requests.post(f"{BASE_URL}/api/trading/orders", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "order" in data
        assert data["order"]["status"] in ["open", "filled", "partially_filled"]
        print(f"PASS: Limit sell order - status: {data['order']['status']}")
    
    def test_12_stop_loss_order(self, auth_token):
        """Test POST /api/trading/orders - stop_loss sell BTC-EUR"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {
            "pair_id": "BTC-EUR",
            "side": "sell",
            "order_type": "stop_loss",
            "quantity": 0.005,
            "stop_price": 55000
        }
        response = requests.post(f"{BASE_URL}/api/trading/orders", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "order" in data
        assert data["order"]["status"] == "pending_trigger"
        print(f"PASS: Stop-loss order - status: {data['order']['status']}")
        return data["order"]["id"]
    
    def test_13_take_profit_order(self, auth_token):
        """Test POST /api/trading/orders - take_profit sell ETH-EUR"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {
            "pair_id": "ETH-EUR",
            "side": "sell",
            "order_type": "take_profit",
            "quantity": 0.05,
            "stop_price": 2500
        }
        response = requests.post(f"{BASE_URL}/api/trading/orders", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "order" in data
        assert data["order"]["status"] == "pending_trigger"
        print(f"PASS: Take-profit order - status: {data['order']['status']}")
    
    def test_14_cancel_order(self, auth_token):
        """Test POST /api/trading/orders/cancel"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        # First create an order to cancel
        payload = {
            "pair_id": "BTC-EUR",
            "side": "sell",
            "order_type": "stop_loss",
            "quantity": 0.001,
            "stop_price": 50000
        }
        create_resp = requests.post(f"{BASE_URL}/api/trading/orders", json=payload, headers=headers)
        assert create_resp.status_code == 200
        order_id = create_resp.json()["order"]["id"]
        
        # Cancel it
        cancel_resp = requests.post(f"{BASE_URL}/api/trading/orders/cancel", 
                                    json={"order_id": order_id}, headers=headers)
        assert cancel_resp.status_code == 200
        print(f"PASS: Cancel order - {order_id}")
    
    def test_15_get_my_orders(self, auth_token):
        """Test GET /api/trading/orders/my"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/trading/orders/my", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "orders" in data
        print(f"PASS: GET /api/trading/orders/my - {len(data['orders'])} orders")


class TestCardManagement:
    """Card Management tests - NIUM API integration"""
    
    def test_16_get_my_cards(self, auth_token):
        """Test GET /api/cards/my-cards"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/cards/my-cards", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "cards" in data
        print(f"PASS: GET /api/cards/my-cards - {len(data['cards'])} cards")
    
    def test_17_create_virtual_card(self, auth_token):
        """Test POST /api/cards/create - virtual visa EUR"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {
            "card_type": "virtual",
            "card_network": "visa",
            "currency": "EUR"
        }
        response = requests.post(f"{BASE_URL}/api/cards/create", json=payload, headers=headers)
        # Accept 200 (created) or 400 (max 3 cards limit)
        assert response.status_code in [200, 400]
        if response.status_code == 200:
            data = response.json()
            assert "card" in data
            assert data["card"]["status"] == "active"
            print(f"PASS: Create virtual card - status: {data['card']['status']}")
        else:
            print(f"PASS: Create virtual card - max limit reached (expected)")
    
    def test_18_create_physical_card_without_address(self, auth_token):
        """Test POST /api/cards/create - physical without shipping_address returns 400"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {
            "card_type": "physical",
            "card_network": "mastercard",
            "currency": "EUR"
        }
        response = requests.post(f"{BASE_URL}/api/cards/create", json=payload, headers=headers)
        assert response.status_code == 400
        print("PASS: Physical card without address returns 400")
    
    def test_19_create_physical_card_with_address(self, auth_token):
        """Test POST /api/cards/create - physical with shipping_address"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {
            "card_type": "physical",
            "card_network": "mastercard",
            "currency": "EUR",
            "shipping_address": {
                "street": "Via Roma 123",
                "city": "Milano",
                "postal_code": "20100",
                "country": "IT"
            }
        }
        response = requests.post(f"{BASE_URL}/api/cards/create", json=payload, headers=headers)
        # Accept 200 (created) or 400 (max 3 cards limit)
        assert response.status_code in [200, 400]
        if response.status_code == 200:
            data = response.json()
            assert "card" in data
            assert data["card"]["status"] == "pending_shipment"
            assert "tracking_number" in data["card"]
            print(f"PASS: Create physical card - tracking: {data['card']['tracking_number']}")
        else:
            print(f"PASS: Create physical card - max limit reached (expected)")
    
    def test_20_card_top_up(self, auth_token):
        """Test POST /api/cards/{card_id}/top-up"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        # Get a card first
        cards_resp = requests.get(f"{BASE_URL}/api/cards/my-cards", headers=headers)
        cards = cards_resp.json().get("cards", [])
        active_cards = [c for c in cards if c.get("status") == "active"]
        
        if not active_cards:
            pytest.skip("No active cards to top up")
        
        card_id = active_cards[0]["id"]
        payload = {"amount_crypto": 0.001, "crypto_asset": "BTC"}
        response = requests.post(f"{BASE_URL}/api/cards/{card_id}/top-up", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "new_balance" in data
        print(f"PASS: Card top-up - new balance: €{data['new_balance']}")
    
    def test_21_card_freeze(self, auth_token):
        """Test POST /api/cards/{card_id}/freeze"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        cards_resp = requests.get(f"{BASE_URL}/api/cards/my-cards", headers=headers)
        cards = cards_resp.json().get("cards", [])
        active_cards = [c for c in cards if c.get("status") == "active"]
        
        if not active_cards:
            pytest.skip("No active cards to freeze")
        
        card_id = active_cards[0]["id"]
        response = requests.post(f"{BASE_URL}/api/cards/{card_id}/freeze", json={}, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ["frozen", "active"]
        print(f"PASS: Card freeze toggle - new status: {data['status']}")
    
    def test_22_get_shipping_status(self, auth_token):
        """Test GET /api/cards/{card_id}/shipping"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        cards_resp = requests.get(f"{BASE_URL}/api/cards/my-cards", headers=headers)
        cards = cards_resp.json().get("cards", [])
        physical_cards = [c for c in cards if c.get("card_type") == "physical"]
        
        if not physical_cards:
            pytest.skip("No physical cards for shipping status")
        
        card_id = physical_cards[0]["id"]
        response = requests.get(f"{BASE_URL}/api/cards/{card_id}/shipping", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "shipping_status" in data
        print(f"PASS: Shipping status - {data['shipping_status']}")


class TestWalletSettlement:
    """Wallet & Settlement tests"""
    
    def test_23_deposit_to_wallet(self, auth_token):
        """Test POST /api/wallet/deposit"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {"asset": "ETH", "amount": 2.0}
        response = requests.post(f"{BASE_URL}/api/wallet/deposit", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "balance" in data
        print(f"PASS: Deposit ETH - balance: {data['balance']}")
    
    def test_24_get_wallet_balances(self, auth_token):
        """Test GET /api/wallet/balances"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/wallet/balances", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "wallets" in data
        assert "total_eur_value" in data
        print(f"PASS: Wallet balances - {len(data['wallets'])} assets, total: €{data['total_eur_value']}")
    
    def test_25_convert_crypto_to_fiat(self, auth_token):
        """Test POST /api/wallet/convert - BTC to EUR"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        # First deposit some BTC
        requests.post(f"{BASE_URL}/api/wallet/deposit", json={"asset": "BTC", "amount": 0.1}, headers=headers)
        
        payload = {"from_asset": "BTC", "to_asset": "EUR", "amount": 0.01}
        response = requests.post(f"{BASE_URL}/api/wallet/convert", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "settlement_id" in data or "conversion" in data or "to_amount" in data
        print(f"PASS: Convert BTC→EUR")
    
    def test_26_convert_crypto_to_crypto(self, auth_token):
        """Test POST /api/wallet/convert - NENO to USDT"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        # First deposit some NENO
        requests.post(f"{BASE_URL}/api/wallet/deposit", json={"asset": "NENO", "amount": 100}, headers=headers)
        
        payload = {"from_asset": "NENO", "to_asset": "USDT", "amount": 10}
        response = requests.post(f"{BASE_URL}/api/wallet/convert", json=payload, headers=headers)
        assert response.status_code == 200
        print(f"PASS: Convert NENO→USDT")
    
    def test_27_convert_fiat_to_crypto(self, auth_token):
        """Test POST /api/wallet/convert - EUR to BTC"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        # First deposit some EUR
        requests.post(f"{BASE_URL}/api/wallet/deposit", json={"asset": "EUR", "amount": 1000}, headers=headers)
        
        payload = {"from_asset": "EUR", "to_asset": "BTC", "amount": 100}
        response = requests.post(f"{BASE_URL}/api/wallet/convert", json=payload, headers=headers)
        assert response.status_code == 200
        print(f"PASS: Convert EUR→BTC")
    
    def test_28_fund_card_from_crypto(self, auth_token):
        """Test POST /api/wallet/fund-card"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        # Get a card
        cards_resp = requests.get(f"{BASE_URL}/api/cards/my-cards", headers=headers)
        cards = cards_resp.json().get("cards", [])
        active_cards = [c for c in cards if c.get("status") == "active"]
        
        if not active_cards:
            pytest.skip("No active cards to fund")
        
        card_id = active_cards[0]["id"]
        # Deposit some crypto first
        requests.post(f"{BASE_URL}/api/wallet/deposit", json={"asset": "BTC", "amount": 0.1}, headers=headers)
        
        payload = {"card_id": card_id, "crypto_asset": "BTC", "crypto_amount": 0.001}
        response = requests.post(f"{BASE_URL}/api/wallet/fund-card", json=payload, headers=headers)
        assert response.status_code == 200
        print(f"PASS: Fund card from crypto")
    
    def test_29_get_settlements(self, auth_token):
        """Test GET /api/wallet/settlements"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/wallet/settlements", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "settlements" in data
        print(f"PASS: GET settlements - {len(data['settlements'])} records")
    
    def test_30_get_conversion_rates(self):
        """Test GET /api/wallet/conversion-rates"""
        response = requests.get(f"{BASE_URL}/api/wallet/conversion-rates")
        assert response.status_code == 200
        data = response.json()
        assert "rates" in data
        assert "supported_assets" in data
        assert len(data["supported_assets"]) >= 10
        print(f"PASS: Conversion rates - {len(data['supported_assets'])} assets")


class TestMultiChainWallet:
    """Multi-Chain Wallet tests"""
    
    def test_31_get_supported_chains(self):
        """Test GET /api/multichain/chains"""
        response = requests.get(f"{BASE_URL}/api/multichain/chains")
        assert response.status_code == 200
        data = response.json()
        assert "chains" in data
        assert len(data["chains"]) >= 3
        chain_keys = [c["key"] for c in data["chains"]]
        assert "ethereum" in chain_keys
        assert "bsc" in chain_keys
        assert "polygon" in chain_keys
        print(f"PASS: Supported chains - {len(data['chains'])} chains")
    
    def test_32_link_wallet(self, auth_token):
        """Test POST /api/multichain/link"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {
            "address": "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD18",
            "chain": "bsc"
        }
        response = requests.post(f"{BASE_URL}/api/multichain/link", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "balances" in data
        print(f"PASS: Link wallet on BSC")
    
    def test_33_get_multichain_balances(self, auth_token):
        """Test GET /api/multichain/balances"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/multichain/balances", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "wallets" in data
        print(f"PASS: Multichain balances - {len(data['wallets'])} wallets")
    
    def test_34_sync_chain(self, auth_token):
        """Test POST /api/multichain/sync"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {"chain": "bsc"}
        response = requests.post(f"{BASE_URL}/api/multichain/sync", json=payload, headers=headers)
        assert response.status_code == 200
        print(f"PASS: Sync BSC chain")
    
    def test_35_get_linked_wallets(self, auth_token):
        """Test GET /api/multichain/linked"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/multichain/linked", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "linked_addresses" in data
        print(f"PASS: Linked wallets - {len(data['linked_addresses'])} addresses")


class TestBankingRails:
    """Banking Rails tests - IBAN/SEPA"""
    
    def test_36_assign_iban(self, auth_token):
        """Test POST /api/banking/iban/assign"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {"currency": "EUR"}
        response = requests.post(f"{BASE_URL}/api/banking/iban/assign", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "iban" in data
        iban_data = data["iban"]
        assert "iban" in iban_data
        assert iban_data["iban"].startswith("NE")  # Simulated IBAN prefix
        print(f"PASS: Assign IBAN - {iban_data['iban']}")
    
    def test_37_get_my_ibans(self, auth_token):
        """Test GET /api/banking/iban"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/banking/iban", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "ibans" in data
        print(f"PASS: GET IBANs - {len(data['ibans'])} IBANs")
    
    def test_38_sepa_deposit(self, auth_token):
        """Test POST /api/banking/sepa/deposit"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {
            "amount": 500.0,
            "sender_iban": "DE89370400440532013000",
            "sender_name": "Test Sender"
        }
        response = requests.post(f"{BASE_URL}/api/banking/sepa/deposit", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "transaction" in data
        assert data["transaction"]["status"] == "completed"
        print(f"PASS: SEPA deposit - €{payload['amount']}")
    
    def test_39_sepa_withdraw(self, auth_token):
        """Test POST /api/banking/sepa/withdraw"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        # First ensure we have EUR balance
        requests.post(f"{BASE_URL}/api/wallet/deposit", json={"asset": "EUR", "amount": 1000}, headers=headers)
        
        payload = {
            "amount": 100.0,
            "destination_iban": "IT60X0542811101000000123456",
            "beneficiary_name": "Test Beneficiary"
        }
        response = requests.post(f"{BASE_URL}/api/banking/sepa/withdraw", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "transaction" in data
        assert "fee" in data["transaction"]
        print(f"PASS: SEPA withdraw - €{data['transaction']['net_amount']} (fee: €{data['transaction']['fee']})")
    
    def test_40_get_banking_transactions(self, auth_token):
        """Test GET /api/banking/transactions"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/banking/transactions", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "transactions" in data
        print(f"PASS: Banking transactions - {len(data['transactions'])} records")
    
    def test_41_admin_banking_overview(self, admin_token):
        """Test GET /api/banking/admin/overview (admin only)"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/banking/admin/overview", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "ibans" in data
        assert "transactions" in data
        print(f"PASS: Admin banking overview - {data['ibans']['total']} IBANs")
    
    def test_42_admin_banking_forbidden_for_user(self, auth_token):
        """Test GET /api/banking/admin/overview returns 403 for regular user"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/banking/admin/overview", headers=headers)
        assert response.status_code == 403
        print(f"PASS: Admin banking overview - 403 for regular user")


class TestPaperTrading:
    """Paper Trading tests"""
    
    def test_43_paper_trade(self, auth_token):
        """Test POST /api/trading/paper/trade"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {
            "pair_id": "NENO-EUR",
            "side": "buy",
            "order_type": "market",
            "quantity": 100
        }
        response = requests.post(f"{BASE_URL}/api/trading/paper/trade", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "trade" in data
        assert data["trade"]["is_paper"] == True
        print(f"PASS: Paper trade - {data['trade']['quantity']} NENO")
    
    def test_44_get_paper_portfolio(self, auth_token):
        """Test GET /api/trading/paper/portfolio"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/trading/paper/portfolio", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "portfolio" in data
        print(f"PASS: Paper portfolio - {data['portfolio'].get('total_trades', 0)} trades")
    
    def test_45_reset_paper_portfolio(self, auth_token):
        """Test DELETE /api/trading/paper/reset"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.delete(f"{BASE_URL}/api/trading/paper/reset", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "€100,000" in data["message"]
        print(f"PASS: Reset paper portfolio")


class TestMarginTrading:
    """Margin Trading tests"""
    
    def test_46_create_margin_account(self, auth_token):
        """Test POST /api/trading/margin/account"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        payload = {"leverage": 5.0}
        response = requests.post(f"{BASE_URL}/api/trading/margin/account", json=payload, headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "max_leverage" in data or "account" in data
        print(f"PASS: Create/update margin account")
    
    def test_47_get_margin_account(self, auth_token):
        """Test GET /api/trading/margin/account"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/trading/margin/account", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "account" in data
        print(f"PASS: Get margin account")
    
    def test_48_get_margin_positions(self, auth_token):
        """Test GET /api/trading/margin/positions"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/trading/margin/positions", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "positions" in data
        print(f"PASS: Get margin positions - {len(data['positions'])} positions")


class TestWebSocketInfra:
    """WebSocket Infrastructure tests"""
    
    def test_49_websocket_status(self):
        """Test GET /api/ws/status"""
        response = requests.get(f"{BASE_URL}/api/ws/status")
        assert response.status_code == 200
        data = response.json()
        assert "active_symbols" in data
        assert "total_connections" in data
        print(f"PASS: WebSocket status - {data['total_connections']} connections")


class TestAdminStats:
    """Admin Statistics tests"""
    
    def test_50_trading_stats_admin(self, admin_token):
        """Test GET /api/trading/stats (admin only)"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/trading/stats", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_trades" in data
        assert "total_orders" in data
        assert "trading_pairs" in data
        print(f"PASS: Trading stats - {data['total_trades']} trades, {data['total_orders']} orders")
    
    def test_51_trading_stats_forbidden_for_user(self, auth_token):
        """Test GET /api/trading/stats returns 403 for regular user"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/trading/stats", headers=headers)
        assert response.status_code == 403
        print(f"PASS: Trading stats - 403 for regular user")


class TestTokensSubscriptions:
    """Token & Subscription tests"""
    
    def test_52_get_tokens(self, auth_token):
        """Test GET /api/tokens/list"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/tokens/list", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "tokens" in data
        print(f"PASS: GET tokens - {len(data['tokens'])} tokens")
    
    def test_53_get_subscription_plans(self, auth_token):
        """Test GET /api/subscriptions/plans/list"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/subscriptions/plans/list", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "plans" in data
        print(f"PASS: GET subscription plans - {len(data['plans'])} plans")


class TestMarketData:
    """Market Data tests"""
    
    def test_54_get_market_data(self):
        """Test GET /api/market-data/coins"""
        response = requests.get(f"{BASE_URL}/api/market-data/coins")
        assert response.status_code == 200
        data = response.json()
        assert "coins" in data
        assert len(data["coins"]) >= 10
        print(f"PASS: GET market data - {len(data['coins'])} coins")


# === FIXTURES ===

@pytest.fixture(scope="class")
def auth_token():
    """Get authentication token for regular user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=REGULAR_USER)
    if response.status_code == 200:
        return response.json()["token"]
    pytest.skip("Authentication failed")


@pytest.fixture(scope="class")
def admin_token():
    """Get authentication token for admin user"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_USER)
    if response.status_code == 200:
        return response.json()["token"]
    pytest.skip("Admin authentication failed")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
