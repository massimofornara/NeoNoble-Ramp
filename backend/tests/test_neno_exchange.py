"""
NENO Exchange Backend API Tests

Tests for the NeoNoble Internal Exchange feature:
- Market info and conversion rates
- Quote generation (buy/sell)
- Buy NENO with various assets
- Sell NENO for various assets
- Off-ramp to card and bank
- Transaction history
- Error handling
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "testchart@example.com"
TEST_PASSWORD = "Test1234!"


def get_auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code != 200:
        return None
    data = response.json()
    # API returns 'token' not 'access_token'
    return data.get("token") or data.get("access_token")


def get_auth_headers():
    """Get headers with auth token"""
    token = get_auth_token()
    if not token:
        return None
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }


class TestNenoExchangeMarket:
    """NENO Exchange market info and quote tests (public endpoints)"""
    
    def test_market_info_returns_neno_price(self):
        """Test 1: GET /api/neno-exchange/market returns neno_eur_price=10000"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/market")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["neno_eur_price"] == 10000, f"Expected NENO price 10000, got {data.get('neno_eur_price')}"
        assert "pairs" in data, "Missing 'pairs' in response"
        assert "supported_assets" in data, "Missing 'supported_assets' in response"
        
        # Verify supported assets
        supported = data["supported_assets"]
        assert len(supported) >= 8, f"Expected at least 8 supported assets, got {len(supported)}"
        
        # Verify required assets are present
        required_assets = ['EUR', 'USD', 'BNB', 'ETH', 'USDT', 'BTC', 'USDC', 'MATIC']
        for asset in required_assets:
            assert asset in supported, f"Missing required asset: {asset}"
        
        print(f"PASS: Market info - NENO price: EUR {data['neno_eur_price']}, {len(supported)} assets, {len(data['pairs'])} pairs")
    
    def test_quote_buy_eur(self):
        """Test 2: GET /api/neno-exchange/quote?direction=buy&asset=EUR&neno_amount=1"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/quote", params={
            "direction": "buy",
            "asset": "EUR",
            "neno_amount": 1
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["direction"] == "buy"
        assert data["neno_amount"] == 1
        assert data["pay_asset"] == "EUR"
        assert data["neno_eur_price"] == 10000
        
        # Fee is 0.3%, so total_cost should be ~10030 EUR
        assert 10020 <= data["total_cost"] <= 10040, f"Expected total_cost ~10030, got {data['total_cost']}"
        assert data["fee_percent"] == 0.3
        
        print(f"PASS: Buy quote EUR - 1 NENO costs {data['total_cost']} EUR (fee: {data['fee']})")
    
    def test_quote_buy_btc(self):
        """Test 3: GET /api/neno-exchange/quote?direction=buy&asset=BTC&neno_amount=1"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/quote", params={
            "direction": "buy",
            "asset": "BTC",
            "neno_amount": 1
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["direction"] == "buy"
        assert data["pay_asset"] == "BTC"
        assert data["rate"] > 0, "Rate should be positive"
        assert data["total_cost"] > 0, "Total cost should be positive"
        
        print(f"PASS: Buy quote BTC - 1 NENO costs {data['total_cost']} BTC (rate: {data['rate']})")
    
    def test_quote_sell_eth(self):
        """Test 4: GET /api/neno-exchange/quote?direction=sell&asset=ETH&neno_amount=1"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/quote", params={
            "direction": "sell",
            "asset": "ETH",
            "neno_amount": 1
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["direction"] == "sell"
        assert data["receive_asset"] == "ETH"
        assert data["net_receive"] > 0, "Net receive should be positive"
        assert data["gross_value"] > data["net_receive"], "Gross should be > net (fee deducted)"
        
        print(f"PASS: Sell quote ETH - 1 NENO = {data['net_receive']} ETH (gross: {data['gross_value']})")
    
    def test_quote_sell_usdt(self):
        """Test 5: GET /api/neno-exchange/quote?direction=sell&asset=USDT&neno_amount=0.5"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/quote", params={
            "direction": "sell",
            "asset": "USDT",
            "neno_amount": 0.5
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["neno_amount"] == 0.5
        assert data["receive_asset"] == "USDT"
        assert data["net_receive"] > 0
        
        print(f"PASS: Sell quote USDT - 0.5 NENO = {data['net_receive']} USDT")
    
    def test_quote_buy_bnb(self):
        """Test 6: GET /api/neno-exchange/quote?direction=buy&asset=BNB&neno_amount=2"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/quote", params={
            "direction": "buy",
            "asset": "BNB",
            "neno_amount": 2
        })
        assert response.status_code == 200
        
        data = response.json()
        assert data["neno_amount"] == 2
        assert data["pay_asset"] == "BNB"
        assert data["total_cost"] > 0
        
        print(f"PASS: Buy quote BNB - 2 NENO costs {data['total_cost']} BNB")


class TestNenoExchangeBuySell:
    """NENO Exchange buy/sell tests (authenticated endpoints)"""
    
    def test_buy_neno_with_eur(self):
        """Test 7: POST /api/neno-exchange/buy {pay_asset:'EUR', neno_amount:0.5}"""
        headers = get_auth_headers()
        assert headers is not None, "Authentication failed"
        
        # First ensure EUR balance
        requests.post(f"{BASE_URL}/api/wallet/deposit", 
            headers=headers,
            json={"asset": "EUR", "amount": 100000}
        )
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/buy",
            headers=headers,
            json={"pay_asset": "EUR", "neno_amount": 0.5}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "transaction" in data
        assert data["transaction"]["type"] == "buy_neno"
        assert data["transaction"]["neno_amount"] == 0.5
        assert data["transaction"]["status"] == "completed"
        assert "balances" in data
        
        print(f"PASS: Buy NENO with EUR - {data['message']}")
    
    def test_buy_neno_with_usdt(self):
        """Test 8: POST /api/neno-exchange/buy {pay_asset:'USDT', neno_amount:0.1}"""
        headers = get_auth_headers()
        assert headers is not None, "Authentication failed"
        
        # First ensure USDT balance
        requests.post(f"{BASE_URL}/api/wallet/deposit", 
            headers=headers,
            json={"asset": "USDT", "amount": 50000}
        )
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/buy",
            headers=headers,
            json={"pay_asset": "USDT", "neno_amount": 0.1}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["transaction"]["pay_asset"] == "USDT"
        assert data["transaction"]["neno_amount"] == 0.1
        
        print(f"PASS: Buy NENO with USDT - {data['message']}")
    
    def test_sell_neno_for_bnb(self):
        """Test 9: POST /api/neno-exchange/sell {receive_asset:'BNB', neno_amount:0.1}"""
        headers = get_auth_headers()
        assert headers is not None, "Authentication failed"
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/sell",
            headers=headers,
            json={"receive_asset": "BNB", "neno_amount": 0.1}
        )
        
        if response.status_code == 400 and "insufficiente" in response.text.lower():
            # Need more NENO - buy some first
            requests.post(f"{BASE_URL}/api/wallet/deposit", 
                headers=headers,
                json={"asset": "EUR", "amount": 100000}
            )
            requests.post(f"{BASE_URL}/api/neno-exchange/buy",
                headers=headers,
                json={"pay_asset": "EUR", "neno_amount": 1}
            )
            response = requests.post(f"{BASE_URL}/api/neno-exchange/sell",
                headers=headers,
                json={"receive_asset": "BNB", "neno_amount": 0.1}
            )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["transaction"]["type"] == "sell_neno"
        assert data["transaction"]["receive_asset"] == "BNB"
        
        print(f"PASS: Sell NENO for BNB - {data['message']}")
    
    def test_sell_neno_for_eth(self):
        """Test 10: POST /api/neno-exchange/sell {receive_asset:'ETH', neno_amount:0.1}"""
        headers = get_auth_headers()
        assert headers is not None, "Authentication failed"
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/sell",
            headers=headers,
            json={"receive_asset": "ETH", "neno_amount": 0.1}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["transaction"]["receive_asset"] == "ETH"
        
        print(f"PASS: Sell NENO for ETH - {data['message']}")
    
    def test_sell_neno_for_eur(self):
        """Test 11: POST /api/neno-exchange/sell {receive_asset:'EUR', neno_amount:0.1}"""
        headers = get_auth_headers()
        assert headers is not None, "Authentication failed"
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/sell",
            headers=headers,
            json={"receive_asset": "EUR", "neno_amount": 0.1}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["transaction"]["receive_asset"] == "EUR"
        
        print(f"PASS: Sell NENO for EUR - {data['message']}")
    
    def test_sell_neno_for_btc(self):
        """Test 12: POST /api/neno-exchange/sell {receive_asset:'BTC', neno_amount:0.05}"""
        headers = get_auth_headers()
        assert headers is not None, "Authentication failed"
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/sell",
            headers=headers,
            json={"receive_asset": "BTC", "neno_amount": 0.05}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["transaction"]["receive_asset"] == "BTC"
        
        print(f"PASS: Sell NENO for BTC - {data['message']}")
    
    def test_sell_neno_for_usdc(self):
        """Test 13: POST /api/neno-exchange/sell {receive_asset:'USDC', neno_amount:0.1}"""
        headers = get_auth_headers()
        assert headers is not None, "Authentication failed"
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/sell",
            headers=headers,
            json={"receive_asset": "USDC", "neno_amount": 0.1}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["transaction"]["receive_asset"] == "USDC"
        
        print(f"PASS: Sell NENO for USDC - {data['message']}")
    
    def test_sell_neno_for_matic(self):
        """Test 14: POST /api/neno-exchange/sell {receive_asset:'MATIC', neno_amount:0.1}"""
        headers = get_auth_headers()
        assert headers is not None, "Authentication failed"
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/sell",
            headers=headers,
            json={"receive_asset": "MATIC", "neno_amount": 0.1}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["transaction"]["receive_asset"] == "MATIC"
        
        print(f"PASS: Sell NENO for MATIC - {data['message']}")


class TestNenoExchangeOfframp:
    """NENO Exchange off-ramp tests (card and bank)"""
    
    def test_offramp_to_card(self):
        """Test 15: POST /api/neno-exchange/offramp to card"""
        headers = get_auth_headers()
        assert headers is not None, "Authentication failed"
        
        # First get user's cards
        cards_response = requests.get(f"{BASE_URL}/api/cards/my-cards", headers=headers)
        cards = cards_response.json().get("cards", [])
        
        active_cards = [c for c in cards if c.get("status") == "active"]
        
        if not active_cards:
            # Create a card first
            create_response = requests.post(f"{BASE_URL}/api/cards/create",
                headers=headers,
                json={"card_type": "virtual", "card_network": "visa", "currency": "EUR"}
            )
            if create_response.status_code == 200:
                card_id = create_response.json().get("card", {}).get("id")
            else:
                pytest.skip("No active cards and couldn't create one")
                return
        else:
            card_id = active_cards[0]["id"]
        
        # Ensure NENO balance
        requests.post(f"{BASE_URL}/api/wallet/deposit", 
            headers=headers,
            json={"asset": "EUR", "amount": 50000}
        )
        requests.post(f"{BASE_URL}/api/neno-exchange/buy",
            headers=headers,
            json={"pay_asset": "EUR", "neno_amount": 0.5}
        )
        
        # Off-ramp to card
        response = requests.post(f"{BASE_URL}/api/neno-exchange/offramp",
            headers=headers,
            json={
                "neno_amount": 0.01,
                "destination": "card",
                "card_id": card_id
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "transaction" in data
        assert data["transaction"]["type"] == "neno_offramp"
        assert data["transaction"]["destination"] == "card"
        assert data["transaction"]["status"] == "completed"
        
        print(f"PASS: Off-ramp to card - {data['message']}")
    
    def test_offramp_to_bank(self):
        """Test 16: POST /api/neno-exchange/offramp to bank (SEPA)"""
        headers = get_auth_headers()
        assert headers is not None, "Authentication failed"
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/offramp",
            headers=headers,
            json={
                "neno_amount": 0.01,
                "destination": "bank",
                "destination_iban": "IT60X0542811101000000123456",
                "beneficiary_name": "Test User"
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["transaction"]["type"] == "neno_offramp"
        assert data["transaction"]["destination"] == "bank"
        assert data["transaction"]["status"] == "processing"  # SEPA is processing
        
        print(f"PASS: Off-ramp to bank - {data['message']}")


class TestNenoExchangeErrors:
    """NENO Exchange error handling tests"""
    
    def test_buy_insufficient_balance(self):
        """Test 17: POST /api/neno-exchange/buy with insufficient balance returns 400"""
        headers = get_auth_headers()
        assert headers is not None, "Authentication failed"
        
        # Try to buy with an asset we don't have much of
        response = requests.post(f"{BASE_URL}/api/neno-exchange/buy",
            headers=headers,
            json={"pay_asset": "SOL", "neno_amount": 1000}  # Very large amount
        )
        
        # Should return 400 for insufficient balance
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        assert "insufficiente" in response.text.lower() or "insufficient" in response.text.lower()
        
        print(f"PASS: Buy with insufficient balance returns 400")
    
    def test_sell_insufficient_neno(self):
        """Test 18: POST /api/neno-exchange/sell with insufficient NENO returns 400"""
        headers = get_auth_headers()
        assert headers is not None, "Authentication failed"
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/sell",
            headers=headers,
            json={"receive_asset": "EUR", "neno_amount": 999999}  # Very large amount
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        assert "insufficiente" in response.text.lower() or "insufficient" in response.text.lower()
        
        print(f"PASS: Sell with insufficient NENO returns 400")
    
    def test_offramp_card_without_card_id(self):
        """Test 19: POST /api/neno-exchange/offramp without card_id for card destination returns 400"""
        headers = get_auth_headers()
        assert headers is not None, "Authentication failed"
        
        response = requests.post(f"{BASE_URL}/api/neno-exchange/offramp",
            headers=headers,
            json={
                "neno_amount": 0.01,
                "destination": "card"
                # Missing card_id
            }
        )
        
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        assert "card_id" in response.text.lower()
        
        print(f"PASS: Off-ramp to card without card_id returns 400")


class TestNenoExchangeTransactions:
    """NENO Exchange transaction history tests"""
    
    def test_get_transactions(self):
        """Test 20: GET /api/neno-exchange/transactions returns transaction history"""
        headers = get_auth_headers()
        assert headers is not None, "Authentication failed"
        
        response = requests.get(f"{BASE_URL}/api/neno-exchange/transactions", headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "transactions" in data
        assert "total" in data
        
        # Should have transactions from previous tests
        if data["total"] > 0:
            tx = data["transactions"][0]
            assert "type" in tx
            assert tx["type"] in ["buy_neno", "sell_neno", "neno_offramp"]
            assert "neno_amount" in tx
            assert "status" in tx
        
        print(f"PASS: Transaction history - {data['total']} transactions found")


class TestNenoConversionRates:
    """Test NENO price consistency in settlement engine"""
    
    def test_conversion_rates_neno_price(self):
        """Test 30: GET /api/wallet/conversion-rates should show NENO at EUR 10000"""
        headers = get_auth_headers()
        if not headers:
            pytest.skip("Auth failed")
        
        response = requests.get(f"{BASE_URL}/api/wallet/conversion-rates", headers=headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        rates = data.get("rates", {})
        
        # Check NENO rate
        if "NENO" in rates:
            neno_eur = rates["NENO"].get("EUR", 0)
            assert neno_eur == 10000, f"Expected NENO/EUR = 10000, got {neno_eur}"
            print(f"PASS: Conversion rates - NENO/EUR = {neno_eur}")
        else:
            print(f"INFO: NENO not in conversion rates, checking market endpoint")
            # Fallback to market endpoint
            market_response = requests.get(f"{BASE_URL}/api/neno-exchange/market")
            assert market_response.status_code == 200
            assert market_response.json()["neno_eur_price"] == 10000
            print(f"PASS: NENO price verified via market endpoint = 10000 EUR")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
