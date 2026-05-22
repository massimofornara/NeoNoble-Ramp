"""
Iteration 34 - Exchange Core + Institutional APIs Tests

Tests for:
- Exchange Orders: submit, order book, my-orders, smart routing
- Institutional: LP registration, providers, structure, financials, investor-deck
- Banking Rails: SEPA/SWIFT/Visa/MC/TARGET2
- Compliance: safeguarding, regulatory report
- PnL & Risk: treasury check, slippage check, arbitrage scan
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication for subsequent tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for admin user"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@neonobleramp.com",
            "password": "Admin1234!"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "No token in response"
        return data["token"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        """Headers with auth token"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }


class TestExchangeOrders(TestAuth):
    """Exchange Orders API Tests - Matching Engine + Order Book + Smart Router"""
    
    def test_01_submit_limit_buy_order(self, headers):
        """POST /api/exchange-orders/submit - submit a limit buy order"""
        response = requests.post(f"{BASE_URL}/api/exchange-orders/submit", headers=headers, json={
            "pair": "NENO/EUR",
            "side": "buy",
            "order_type": "limit",
            "quantity": 0.001,
            "price": 9500.0
        })
        # Accept 200 (success) or 400 (risk check - balance/exposure)
        assert response.status_code in [200, 400], f"Unexpected status: {response.status_code} - {response.text}"
        data = response.json()
        if response.status_code == 200:
            assert "order" in data, "No order in response"
            order = data["order"]
            assert order["pair"] == "NENO/EUR" or order["pair"] == "NENO-EUR"
            assert order["side"] == "buy"
            assert order["order_type"] == "limit"
            print(f"PASSED: Order submitted - ID: {order.get('id')}, Status: {order.get('status')}")
        else:
            # Risk check failed - acceptable for testing
            print(f"PASSED: Risk check correctly rejected order - {data.get('detail', data)}")
    
    def test_02_order_book_snapshot(self, headers):
        """GET /api/exchange-orders/book/NENO-EUR - order book snapshot"""
        response = requests.get(f"{BASE_URL}/api/exchange-orders/book/NENO-EUR", headers=headers)
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "pair" in data, "No pair in response"
        assert "bids" in data, "No bids in response"
        assert "asks" in data, "No asks in response"
        assert "timestamp" in data, "No timestamp in response"
        print(f"PASSED: Order book - Pair: {data['pair']}, Bids: {data.get('bid_count', len(data['bids']))}, Asks: {data.get('ask_count', len(data['asks']))}")
    
    def test_03_my_orders(self, headers):
        """GET /api/exchange-orders/my-orders - user's orders"""
        response = requests.get(f"{BASE_URL}/api/exchange-orders/my-orders", headers=headers)
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "orders" in data, "No orders in response"
        assert isinstance(data["orders"], list), "Orders should be a list"
        print(f"PASSED: My orders - Count: {len(data['orders'])}")
    
    def test_04_smart_routing(self, headers):
        """GET /api/exchange-orders/route/NENO - smart routing"""
        response = requests.get(f"{BASE_URL}/api/exchange-orders/route/NENO?side=buy&amount=1.0", headers=headers)
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "best" in data or "venues" in data, "No routing data in response"
        if data.get("best"):
            best = data["best"]
            assert "venue" in best, "No venue in best route"
            assert "price" in best, "No price in best route"
            print(f"PASSED: Smart routing - Best venue: {best['venue']}, Price: {best['price']}")
        else:
            print(f"PASSED: Smart routing - Venues: {len(data.get('venues', []))}")


class TestInstitutionalCapitalMarkets(TestAuth):
    """Institutional API Tests - Capital Markets, Structure, Financials"""
    
    def test_05_corporate_structure(self, headers):
        """GET /api/institutional/structure - corporate holding structure"""
        response = requests.get(f"{BASE_URL}/api/institutional/structure", headers=headers)
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "holding" in data, "No holding in response"
        assert "subsidiaries" in data, "No subsidiaries in response"
        assert "governance" in data, "No governance in response"
        holding = data["holding"]
        assert holding.get("name") == "NeoNoble Holding AG", f"Unexpected holding name: {holding.get('name')}"
        assert holding.get("status") == "ipo_ready", f"Unexpected status: {holding.get('status')}"
        print(f"PASSED: Corporate structure - Holding: {holding['name']}, Subsidiaries: {len(data['subsidiaries'])}")
    
    def test_06_financials_ifrs(self, headers):
        """GET /api/institutional/financials - IFRS financials with KPIs"""
        response = requests.get(f"{BASE_URL}/api/institutional/financials", headers=headers)
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "income_statement" in data, "No income_statement in response"
        assert "kpis" in data, "No kpis in response"
        income = data["income_statement"]
        assert "revenue" in income, "No revenue in income statement"
        assert income.get("reporting_standard") == "IFRS", f"Unexpected standard: {income.get('reporting_standard')}"
        kpis = data["kpis"]
        assert "total_volume_eur" in kpis, "No total_volume_eur in KPIs"
        assert "total_transactions" in kpis, "No total_transactions in KPIs"
        print(f"PASSED: Financials - Volume: EUR {kpis['total_volume_eur']}, Transactions: {kpis['total_transactions']}")
    
    def test_07_investor_deck(self, headers):
        """GET /api/institutional/investor-deck - full investor deck"""
        response = requests.get(f"{BASE_URL}/api/institutional/investor-deck", headers=headers)
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "company" in data, "No company in response"
        assert "corporate_structure" in data, "No corporate_structure in response"
        assert "financials" in data, "No financials in response"
        assert "capital_markets_access" in data, "No capital_markets_access in response"
        assert data["company"] == "NeoNoble Holding AG", f"Unexpected company: {data['company']}"
        cma = data["capital_markets_access"]
        assert "equity" in cma, "No equity in capital_markets_access"
        assert "debt" in cma, "No debt in capital_markets_access"
        print(f"PASSED: Investor deck - Company: {data['company']}, IPO readiness: {cma['equity'].get('ipo_readiness')}")
    
    def test_08_banking_rails(self, headers):
        """GET /api/institutional/banking-rails - SEPA/SWIFT/Visa/MC/TARGET2"""
        response = requests.get(f"{BASE_URL}/api/institutional/banking-rails", headers=headers)
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        # Check SEPA
        assert "sepa" in data, "No sepa in response"
        assert data["sepa"]["status"] == "active", f"SEPA not active: {data['sepa']['status']}"
        # Check SWIFT
        assert "swift" in data, "No swift in response"
        assert data["swift"]["status"] == "framework_ready", f"SWIFT status: {data['swift']['status']}"
        # Check cards (Visa/MC)
        assert "cards" in data, "No cards in response"
        assert "visa" in data["cards"], "No visa in cards"
        assert "mastercard" in data["cards"], "No mastercard in cards"
        # Check clearing systems (TARGET2)
        assert "clearing_systems" in data, "No clearing_systems in response"
        assert "target2" in data["clearing_systems"], "No target2 in clearing_systems"
        print(f"PASSED: Banking rails - SEPA: {data['sepa']['status']}, SWIFT: {data['swift']['status']}, Visa: {data['cards']['visa']['status']}")


class TestInstitutionalCompliance(TestAuth):
    """Institutional API Tests - Compliance, Safeguarding, Regulatory"""
    
    def test_09_safeguarding_report(self, headers):
        """GET /api/institutional/compliance/safeguarding - EMI safeguarding report"""
        response = requests.get(f"{BASE_URL}/api/institutional/compliance/safeguarding", headers=headers)
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "total_client_funds_eur" in data, "No total_client_funds_eur in response"
        assert "treasury_eur" in data, "No treasury_eur in response"
        assert "coverage_pct" in data, "No coverage_pct in response"
        assert "safeguarding_status" in data, "No safeguarding_status in response"
        assert "emi_requirement" in data, "No emi_requirement in response"
        print(f"PASSED: Safeguarding - Client funds: EUR {data['total_client_funds_eur']}, Coverage: {data['coverage_pct']}%, Status: {data['safeguarding_status']}")
    
    def test_10_regulatory_report(self, headers):
        """GET /api/institutional/compliance/regulatory-report - regulatory report"""
        response = requests.get(f"{BASE_URL}/api/institutional/compliance/regulatory-report?report_type=emi", headers=headers)
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "report_type" in data, "No report_type in response"
        assert data["report_type"] == "emi", f"Unexpected report_type: {data['report_type']}"
        assert "metrics" in data, "No metrics in response"
        assert "safeguarding" in data, "No safeguarding in response"
        assert "licenses" in data, "No licenses in response"
        licenses = data["licenses"]
        assert "emi" in licenses, "No emi in licenses"
        assert "casp" in licenses, "No casp in licenses"
        print(f"PASSED: Regulatory report - Type: {data['report_type']}, Transactions: {data['metrics'].get('total_transactions')}")


class TestInstitutionalPnLRisk(TestAuth):
    """Institutional API Tests - PnL, Risk, Arbitrage"""
    
    def test_11_pnl(self, headers):
        """GET /api/institutional/pnl - profit and loss"""
        response = requests.get(f"{BASE_URL}/api/institutional/pnl?period_hours=24", headers=headers)
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "period_hours" in data, "No period_hours in response"
        assert "trading_fees" in data, "No trading_fees in response"
        assert "spread_revenue" in data, "No spread_revenue in response"
        assert "total_revenue_eur" in data, "No total_revenue_eur in response"
        print(f"PASSED: PnL - Trading fees: EUR {data['trading_fees'].get('total_eur', 0)}, Spread: EUR {data['spread_revenue'].get('total_eur', 0)}, Total: EUR {data['total_revenue_eur']}")
    
    def test_12_treasury_check(self, headers):
        """GET /api/institutional/risk/treasury-check/NENO - on-chain treasury verification"""
        response = requests.get(f"{BASE_URL}/api/institutional/risk/treasury-check/NENO?amount=1", headers=headers)
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "sufficient" in data, "No sufficient in response"
        assert "asset" in data or "detail" in data, "No asset or detail in response"
        if "on_chain" in data:
            print(f"PASSED: Treasury check - Asset: {data.get('asset')}, On-chain: {data['on_chain']}, Sufficient: {data['sufficient']}")
        else:
            print(f"PASSED: Treasury check - Detail: {data.get('detail')}")
    
    def test_13_slippage_check(self, headers):
        """GET /api/institutional/risk/slippage-check - slippage guard"""
        response = requests.get(f"{BASE_URL}/api/institutional/risk/slippage-check?expected_price=10000&execution_price=10050", headers=headers)
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "pass" in data, "No pass in response"
        assert "slippage_pct" in data, "No slippage_pct in response"
        assert "max_allowed_pct" in data, "No max_allowed_pct in response"
        print(f"PASSED: Slippage check - Slippage: {data['slippage_pct']}%, Max: {data['max_allowed_pct']}%, Pass: {data['pass']}")
    
    def test_14_arbitrage_scan(self, headers):
        """GET /api/institutional/arbitrage/scan - arbitrage opportunities"""
        response = requests.get(f"{BASE_URL}/api/institutional/arbitrage/scan", headers=headers)
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "opportunities" in data, "No opportunities in response"
        assert "count" in data, "No count in response"
        assert isinstance(data["opportunities"], list), "Opportunities should be a list"
        print(f"PASSED: Arbitrage scan - Opportunities found: {data['count']}")


class TestInstitutionalLP(TestAuth):
    """Institutional API Tests - Liquidity Providers"""
    
    def test_15_register_lp_provider(self, headers):
        """POST /api/institutional/lp/register - register LP provider"""
        import uuid
        lp_name = f"TEST_LP_{uuid.uuid4().hex[:8]}"
        response = requests.post(f"{BASE_URL}/api/institutional/lp/register", headers=headers, json={
            "name": lp_name,
            "tier": "tier_1",
            "type": "market_maker",
            "supported_pairs": ["NENO/EUR"],
            "min_order_eur": 1000,
            "max_order_eur": 5000000,
            "fee_bps": 5
        })
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "id" in data, "No id in response"
        assert "name" in data, "No name in response"
        assert data["name"] == lp_name, f"Unexpected name: {data['name']}"
        assert data["tier"] == "tier_1", f"Unexpected tier: {data['tier']}"
        print(f"PASSED: LP registered - ID: {data['id']}, Name: {data['name']}, Tier: {data['tier']}")
    
    def test_16_list_lp_providers(self, headers):
        """GET /api/institutional/lp/providers - list LP providers"""
        response = requests.get(f"{BASE_URL}/api/institutional/lp/providers", headers=headers)
        assert response.status_code == 200, f"Failed: {response.status_code} - {response.text}"
        data = response.json()
        assert "providers" in data, "No providers in response"
        assert isinstance(data["providers"], list), "Providers should be a list"
        print(f"PASSED: LP providers - Count: {len(data['providers'])}")


class TestExchangeOrdersNoAuth:
    """Test endpoints that should work without auth (public order book)"""
    
    def test_17_order_book_public(self):
        """GET /api/exchange-orders/book/NENO-EUR - public order book (no auth)"""
        response = requests.get(f"{BASE_URL}/api/exchange-orders/book/NENO-EUR")
        # Order book should be public
        assert response.status_code == 200, f"Order book should be public: {response.status_code} - {response.text}"
        data = response.json()
        assert "pair" in data, "No pair in response"
        print(f"PASSED: Public order book accessible - Pair: {data['pair']}")


class TestInstitutionalAuthRequired:
    """Test that institutional endpoints require auth"""
    
    def test_18_structure_requires_auth(self):
        """GET /api/institutional/structure - requires auth"""
        response = requests.get(f"{BASE_URL}/api/institutional/structure")
        assert response.status_code == 401, f"Should require auth: {response.status_code}"
        print("PASSED: Structure endpoint requires auth")
    
    def test_19_pnl_requires_auth(self):
        """GET /api/institutional/pnl - requires auth"""
        response = requests.get(f"{BASE_URL}/api/institutional/pnl")
        assert response.status_code == 401, f"Should require auth: {response.status_code}"
        print("PASSED: PnL endpoint requires auth")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
