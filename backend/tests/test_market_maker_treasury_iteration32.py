"""
Market Maker Treasury Tests - Iteration 32
Tests Treasury = Massimo's Account (TREASURY_USER_ID)

Key validations:
1. Treasury endpoints return owner=massimo.fornara.2212@gmail.com
2. Treasury shows combined internal_balance + onchain_balance
3. NENO shows ~397 onchain, EUR shows ~29640 internal, ETH ~884 internal
4. Buy/Sell trades ACTUALLY update Massimo's EUR wallet balance
5. Crypto off-ramp fails gracefully with insufficient USDT message
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-chain-wallet-14.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"
TREASURY_OWNER_EMAIL = "massimo.fornara.2212@gmail.com"
TREASURY_USER_ID = "de9a3781-b9d2-4b37-922d-2f6959e0f529"

# Global session to reuse auth token
_session = None
_token = None


def get_auth_session():
    """Get authenticated session, reusing token if available"""
    global _session, _token
    
    if _session is not None and _token is not None:
        return _session, _token
    
    _session = requests.Session()
    response = _session.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    
    if response.status_code == 429:
        # Rate limited, wait and retry
        retry_after = response.json().get("retry_after", 30)
        print(f"Rate limited, waiting {retry_after}s...")
        time.sleep(retry_after + 2)
        response = _session.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
    
    assert response.status_code == 200, f"Login failed: {response.text}"
    _token = response.json()["token"]  # Note: "token" not "access_token"
    _session.headers.update({"Authorization": f"Bearer {_token}"})
    return _session, _token


class TestMarketMakerPricing:
    """Test Market Maker pricing endpoint (PUBLIC)"""
    
    def test_01_mm_pricing_public(self):
        """GET /api/market-maker/pricing - returns bid, ask, mid_price, spread_bps, treasury_neno, treasury_owner"""
        response = requests.get(f"{BASE_URL}/api/market-maker/pricing")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Validate required fields
        assert "bid" in data, "Missing bid"
        assert "ask" in data, "Missing ask"
        assert "mid_price" in data, "Missing mid_price"
        assert "spread_bps" in data, "Missing spread_bps"
        assert "treasury_neno" in data, "Missing treasury_neno"
        assert "treasury_owner" in data, "Missing treasury_owner"
        assert "inventory_ratio" in data, "Missing inventory_ratio"
        assert "inventory_skew" in data, "Missing inventory_skew"
        
        # Validate treasury_neno is ~397
        assert data["treasury_neno"] >= 390 and data["treasury_neno"] <= 410, f"Expected treasury_neno ~397, got {data['treasury_neno']}"
        
        # Validate treasury_owner is Massimo's email
        assert TREASURY_OWNER_EMAIL in data["treasury_owner"], f"Expected treasury_owner to contain {TREASURY_OWNER_EMAIL}, got {data['treasury_owner']}"
        
        print(f"MM Pricing: bid={data['bid']}, ask={data['ask']}, mid={data['mid_price']}, spread={data['spread_bps']}bps")
        print(f"Treasury: NENO={data['treasury_neno']}, owner={data['treasury_owner']}")


class TestMarketMakerTreasury:
    """Test Market Maker treasury endpoints (AUTH required)"""
    
    def test_02_mm_treasury_full(self):
        """GET /api/market-maker/treasury - returns owner=massimo email, assets with internal+onchain balances"""
        session, _ = get_auth_session()
        response = session.get(f"{BASE_URL}/api/market-maker/treasury")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Validate owner
        assert "owner" in data, "Missing owner"
        assert TREASURY_OWNER_EMAIL in data["owner"], f"Expected owner to contain {TREASURY_OWNER_EMAIL}, got {data['owner']}"
        
        # Validate assets structure
        assert "assets" in data, "Missing assets"
        assets = data["assets"]
        
        # Check NENO asset
        assert "NENO" in assets, "Missing NENO in treasury assets"
        neno = assets["NENO"]
        assert "internal_balance" in neno, "Missing internal_balance for NENO"
        assert "onchain_balance" in neno, "Missing onchain_balance for NENO"
        assert "amount" in neno, "Missing amount for NENO"
        # NENO should show ~397 onchain
        assert neno["onchain_balance"] >= 390 and neno["onchain_balance"] <= 410, f"Expected NENO onchain ~397, got {neno['onchain_balance']}"
        
        # Check EUR asset
        assert "EUR" in assets, "Missing EUR in treasury assets"
        eur = assets["EUR"]
        assert "internal_balance" in eur, "Missing internal_balance for EUR"
        # EUR should show ~29640 internal
        assert eur["internal_balance"] >= 29000, f"Expected EUR internal ~29640, got {eur['internal_balance']}"
        
        # Check ETH asset
        if "ETH" in assets:
            eth = assets["ETH"]
            assert "internal_balance" in eth, "Missing internal_balance for ETH"
            # ETH should show ~884 internal
            print(f"ETH internal_balance: {eth['internal_balance']}")
        
        print(f"Treasury owner: {data['owner']}")
        print(f"NENO: amount={neno['amount']}, internal={neno['internal_balance']}, onchain={neno['onchain_balance']}")
        print(f"EUR: amount={eur['amount']}, internal={eur['internal_balance']}")
    
    def test_03_mm_treasury_neno_asset(self):
        """GET /api/market-maker/treasury/NENO - returns NENO with amount=397, onchain_balance=397, internal_balance=0"""
        session, _ = get_auth_session()
        response = session.get(f"{BASE_URL}/api/market-maker/treasury/NENO")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["asset"] == "NENO", f"Expected asset=NENO, got {data['asset']}"
        assert "amount" in data, "Missing amount"
        assert "onchain_balance" in data, "Missing onchain_balance"
        assert "internal_balance" in data, "Missing internal_balance"
        
        # NENO should be ~397 onchain, 0 internal
        assert data["onchain_balance"] >= 390 and data["onchain_balance"] <= 410, f"Expected onchain ~397, got {data['onchain_balance']}"
        assert data["internal_balance"] == 0 or data["internal_balance"] < 1, f"Expected internal ~0, got {data['internal_balance']}"
        
        print(f"NENO Treasury: amount={data['amount']}, onchain={data['onchain_balance']}, internal={data['internal_balance']}")
    
    def test_04_mm_treasury_eur_asset(self):
        """GET /api/market-maker/treasury/EUR - returns EUR with amount=~29640, internal_balance=~29640"""
        session, _ = get_auth_session()
        response = session.get(f"{BASE_URL}/api/market-maker/treasury/EUR")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["asset"] == "EUR", f"Expected asset=EUR, got {data['asset']}"
        assert "amount" in data, "Missing amount"
        assert "internal_balance" in data, "Missing internal_balance"
        
        # EUR should be ~29640 internal
        assert data["internal_balance"] >= 29000, f"Expected internal ~29640, got {data['internal_balance']}"
        
        print(f"EUR Treasury: amount={data['amount']}, internal={data['internal_balance']}")


class TestMarketMakerPnLRisk:
    """Test Market Maker PnL and Risk endpoints (AUTH required)"""
    
    def test_05_mm_pnl_report(self):
        """GET /api/market-maker/pnl - returns treasury_owner=massimo email, trade data"""
        session, _ = get_auth_session()
        response = session.get(f"{BASE_URL}/api/market-maker/pnl")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "treasury_owner" in data, "Missing treasury_owner"
        assert TREASURY_OWNER_EMAIL in data["treasury_owner"], f"Expected treasury_owner to contain {TREASURY_OWNER_EMAIL}, got {data['treasury_owner']}"
        
        print(f"PnL Report: treasury_owner={data['treasury_owner']}, trade_count={data.get('trade_count', 0)}")
    
    def test_06_mm_risk_dashboard(self):
        """GET /api/market-maker/risk - returns treasury_owner=massimo email, risk_level, inventory metrics"""
        session, _ = get_auth_session()
        response = session.get(f"{BASE_URL}/api/market-maker/risk")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "treasury_owner" in data, "Missing treasury_owner"
        assert TREASURY_OWNER_EMAIL in data["treasury_owner"], f"Expected treasury_owner to contain {TREASURY_OWNER_EMAIL}, got {data['treasury_owner']}"
        assert "risk_level" in data, "Missing risk_level"
        assert "neno_inventory" in data, "Missing neno_inventory"
        assert "inventory_ratio" in data, "Missing inventory_ratio"
        
        print(f"Risk Dashboard: treasury_owner={data['treasury_owner']}, risk_level={data['risk_level']}, neno_inventory={data['neno_inventory']}")


class TestNenoExchangeWithMM:
    """Test NENO Exchange endpoints with Market Maker integration"""
    
    def test_07_neno_exchange_price(self):
        """GET /api/neno-exchange/price - returns bid/ask/spread/mid_price/pricing_model=market_maker_bid_ask"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/price")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "bid" in data, "Missing bid"
        assert "ask" in data, "Missing ask"
        assert "spread_bps" in data, "Missing spread_bps"
        assert "mid_price" in data, "Missing mid_price"
        assert "pricing_model" in data, "Missing pricing_model"
        assert data["pricing_model"] == "market_maker_bid_ask", f"Expected pricing_model=market_maker_bid_ask, got {data['pricing_model']}"
        
        print(f"NENO Price: bid={data['bid']}, ask={data['ask']}, mid={data['mid_price']}, model={data['pricing_model']}")
    
    def test_08_neno_exchange_quote_buy(self):
        """GET /api/neno-exchange/quote?direction=buy - uses ask price, shows mm_bid, mm_ask, mm_spread_bps, mm_mid_price"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/quote?direction=buy&asset=EUR&neno_amount=0.001")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "mm_bid" in data, "Missing mm_bid"
        assert "mm_ask" in data, "Missing mm_ask"
        assert "mm_spread_bps" in data, "Missing mm_spread_bps"
        assert "mm_mid_price" in data, "Missing mm_mid_price"
        assert "neno_eur_price" in data, "Missing neno_eur_price"
        
        # Buy should use ask price
        assert data["neno_eur_price"] == data["mm_ask"], f"Buy should use ask price: neno_eur_price={data['neno_eur_price']}, mm_ask={data['mm_ask']}"
        
        print(f"Quote Buy: price={data['neno_eur_price']} (ask), mm_bid={data['mm_bid']}, mm_ask={data['mm_ask']}, spread={data['mm_spread_bps']}bps")
    
    def test_09_neno_exchange_quote_sell(self):
        """GET /api/neno-exchange/quote?direction=sell - uses bid price"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/quote?direction=sell&asset=EUR&neno_amount=0.001")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "mm_bid" in data, "Missing mm_bid"
        assert "mm_ask" in data, "Missing mm_ask"
        assert "neno_eur_price" in data, "Missing neno_eur_price"
        
        # Sell should use bid price
        assert data["neno_eur_price"] == data["mm_bid"], f"Sell should use bid price: neno_eur_price={data['neno_eur_price']}, mm_bid={data['mm_bid']}"
        
        print(f"Quote Sell: price={data['neno_eur_price']} (bid), mm_bid={data['mm_bid']}, mm_ask={data['mm_ask']}")
    
    def test_10_neno_exchange_market(self):
        """GET /api/neno-exchange/market - returns bid/ask/spread/treasury_neno/pricing_model=market_maker"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/market")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "bid" in data, "Missing bid"
        assert "ask" in data, "Missing ask"
        assert "spread_bps" in data, "Missing spread_bps"
        assert "treasury_neno" in data, "Missing treasury_neno"
        assert "pricing_model" in data, "Missing pricing_model"
        assert data["pricing_model"] == "market_maker", f"Expected pricing_model=market_maker, got {data['pricing_model']}"
        
        print(f"Market: bid={data['bid']}, ask={data['ask']}, treasury_neno={data['treasury_neno']}, model={data['pricing_model']}")


class TestTreasuryBalanceChanges:
    """Test that buy/sell trades ACTUALLY update Massimo's wallet balances"""
    
    def test_11_buy_neno_updates_treasury_eur(self):
        """POST /api/neno-exchange/buy - should INCREASE Massimo's EUR balance"""
        session, _ = get_auth_session()
        
        # Get treasury EUR before trade
        response = session.get(f"{BASE_URL}/api/market-maker/treasury/EUR")
        assert response.status_code == 200
        eur_before = response.json()["internal_balance"]
        print(f"Treasury EUR before buy: {eur_before}")
        
        # Execute buy (user pays EUR, receives NENO)
        # When user buys NENO, Treasury SELLS NENO and RECEIVES EUR
        buy_response = session.post(f"{BASE_URL}/api/neno-exchange/buy", 
            json={"pay_asset": "EUR", "neno_amount": 0.001}
        )
        assert buy_response.status_code == 200, f"Buy failed: {buy_response.text}"
        
        buy_data = buy_response.json()
        assert "market_maker" in buy_data, "Missing market_maker in response"
        print(f"Buy result: {buy_data.get('message')}")
        print(f"Market Maker info: {buy_data.get('market_maker')}")
        
        # Wait a moment for DB to update
        time.sleep(0.5)
        
        # Get treasury EUR after trade
        response = session.get(f"{BASE_URL}/api/market-maker/treasury/EUR")
        assert response.status_code == 200
        eur_after = response.json()["internal_balance"]
        print(f"Treasury EUR after buy: {eur_after}")
        
        # Treasury EUR should INCREASE (user paid EUR to treasury)
        delta = eur_after - eur_before
        print(f"Treasury EUR delta: {delta}")
        assert delta > 0, f"Expected Treasury EUR to INCREASE after buy, but delta={delta}"
    
    def test_12_sell_neno_updates_treasury_eur(self):
        """POST /api/neno-exchange/sell - should DECREASE Massimo's EUR balance"""
        session, _ = get_auth_session()
        
        # Get treasury EUR before trade
        response = session.get(f"{BASE_URL}/api/market-maker/treasury/EUR")
        assert response.status_code == 200
        eur_before = response.json()["internal_balance"]
        print(f"Treasury EUR before sell: {eur_before}")
        
        # Execute sell (user sells NENO, receives EUR)
        # When user sells NENO, Treasury BUYS NENO and PAYS EUR
        sell_response = session.post(f"{BASE_URL}/api/neno-exchange/sell", 
            json={"receive_asset": "EUR", "neno_amount": 0.001}
        )
        assert sell_response.status_code == 200, f"Sell failed: {sell_response.text}"
        
        sell_data = sell_response.json()
        assert "market_maker" in sell_data, "Missing market_maker in response"
        print(f"Sell result: {sell_data.get('message')}")
        print(f"Market Maker info: {sell_data.get('market_maker')}")
        
        # Wait a moment for DB to update
        time.sleep(0.5)
        
        # Get treasury EUR after trade
        response = session.get(f"{BASE_URL}/api/market-maker/treasury/EUR")
        assert response.status_code == 200
        eur_after = response.json()["internal_balance"]
        print(f"Treasury EUR after sell: {eur_after}")
        
        # Treasury EUR should DECREASE (treasury paid EUR to user)
        delta = eur_after - eur_before
        print(f"Treasury EUR delta: {delta}")
        assert delta < 0, f"Expected Treasury EUR to DECREASE after sell, but delta={delta}"


class TestCryptoOfframpFallback:
    """Test crypto off-ramp fallback when NIUM is not configured"""
    
    def test_13_crypto_offramp_insufficient_usdt(self):
        """POST /api/neno-exchange/offramp with crypto destination - should fail with insufficient USDT message"""
        session, _ = get_auth_session()
        
        # Attempt crypto off-ramp
        response = session.post(f"{BASE_URL}/api/neno-exchange/offramp",
            json={
                "neno_amount": 0.001,
                "destination": "crypto",
                "destination_wallet": "0x1234567890123456789012345678901234567890",
                "preferred_stable": "USDT"
            }
        )
        
        # Should fail with 500 error containing "insufficiente" message
        assert response.status_code == 500, f"Expected 500, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, "Missing detail in error response"
        # Check for Italian "insufficiente" message
        assert "insufficiente" in data["detail"].lower() or "insufficient" in data["detail"].lower(), \
            f"Expected 'insufficiente' in error message, got: {data['detail']}"
        
        print(f"Crypto off-ramp correctly failed: {data['detail']}")
    
    def test_14_crypto_offramp_usdc_also_fails(self):
        """POST /api/neno-exchange/offramp with USDC - should also fail with insufficient balance"""
        session, _ = get_auth_session()
        
        response = session.post(f"{BASE_URL}/api/neno-exchange/offramp",
            json={
                "neno_amount": 0.001,
                "destination": "crypto",
                "destination_wallet": "0x1234567890123456789012345678901234567890",
                "preferred_stable": "USDC"
            }
        )
        
        # Should fail with 500 error
        assert response.status_code == 500, f"Expected 500, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "detail" in data, "Missing detail in error response"
        print(f"USDC off-ramp correctly failed: {data['detail']}")


class TestTreasuryAssetBreakdown:
    """Test treasury asset breakdown with internal+onchain balances"""
    
    def test_15_treasury_usdt_balance(self):
        """GET /api/market-maker/treasury/USDT - should show 0 balance (explains crypto off-ramp failure)"""
        session, _ = get_auth_session()
        response = session.get(f"{BASE_URL}/api/market-maker/treasury/USDT")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["asset"] == "USDT", f"Expected asset=USDT, got {data['asset']}"
        
        # USDT should be 0 or very low
        total = data.get("amount", 0)
        print(f"USDT Treasury: amount={total}, internal={data.get('internal_balance', 0)}, onchain={data.get('onchain_balance', 0)}")
        
        # This explains why crypto off-ramp fails
        assert total < 1, f"Expected USDT ~0, got {total}"
    
    def test_16_treasury_bnb_balance(self):
        """GET /api/market-maker/treasury/BNB - check BNB balance"""
        session, _ = get_auth_session()
        response = session.get(f"{BASE_URL}/api/market-maker/treasury/BNB")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["asset"] == "BNB", f"Expected asset=BNB, got {data['asset']}"
        
        print(f"BNB Treasury: amount={data.get('amount', 0)}, internal={data.get('internal_balance', 0)}, onchain={data.get('onchain_balance', 0)}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
