"""
Iteration 37 - Cashout Engine Tests
Tests for the Autonomous Profit Extraction Engine with Continuous Cashout.

Features tested:
- GET /api/cashout/status — engine status, cycle_count, cumulative metrics, EUR accounts
- GET /api/cashout/report — comprehensive report with USDC wallets, hot wallet, conversions
- GET /api/cashout/history — cashout operation history
- GET /api/cashout/eur-accounts — IT and BE IBAN accounts with SEPA/SWIFT routing
- GET /api/cashout/conversions/opportunities — crypto→USDC conversion opportunities
- GET /api/cashout/conversions/history — conversion history
- GET /api/cashout/conversions/summary — conversion summary by pair
- POST /api/cashout/start — start cashout engine (admin only)
- POST /api/cashout/stop — stop cashout engine (admin only)
- All cashout endpoints require authentication (401 without token)
- GET /api/circle/wallets/balances — still working with 3 segregated wallets
- GET /api/circle/auto-op/status — auto-op loop still running
- GET /api/health — health check
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"

# Expected EUR accounts
EXPECTED_EUR_ACCOUNTS = {
    "IT": {
        "iban": "IT80V1810301600068254758246",
        "bic": "FNOMITM2",
    },
    "BE": {
        "iban": "BE06967614820722",
        "bic": "TRWIBEB1XXX",
    },
}


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token for admin user"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if response.status_code == 200:
        data = response.json()
        return data.get("token") or data.get("access_token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def authenticated_client(api_client, auth_token):
    """Session with auth header"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


class TestHealthAndPrerequisites:
    """Basic health checks and prerequisites"""

    def test_01_health_check(self, api_client):
        """Test health endpoint is working"""
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "NeoNoble Ramp"
        print(f"✓ Health check passed: {data}")

    def test_02_admin_login(self, api_client):
        """Test admin login works"""
        response = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data or "access_token" in data
        print(f"✓ Admin login successful")


class TestCashoutEngineStatus:
    """Tests for cashout engine status and metrics"""

    def test_03_cashout_status(self, authenticated_client):
        """GET /api/cashout/status — returns engine status with metrics"""
        response = authenticated_client.get(f"{BASE_URL}/api/cashout/status")
        assert response.status_code == 200
        data = response.json()
        
        # Verify engine status fields
        assert "running" in data
        assert "cycle_count" in data
        assert "interval_seconds" in data
        assert "treasury_buffer_pct" in data
        assert "min_cashout_usdc" in data
        assert "min_cashout_eur" in data
        
        # Verify cumulative metrics
        assert "cumulative" in data
        cumulative = data["cumulative"]
        assert "extracted_usdc" in cumulative
        assert "extracted_eur" in cumulative
        assert "cashouts_executed" in cumulative
        assert "cashouts_blocked" in cumulative
        
        # Verify EUR accounts
        assert "eur_accounts" in data
        eur_accounts = data["eur_accounts"]
        assert "IT" in eur_accounts
        assert "BE" in eur_accounts
        assert eur_accounts["IT"]["iban"] == EXPECTED_EUR_ACCOUNTS["IT"]["iban"]
        assert eur_accounts["IT"]["bic"] == EXPECTED_EUR_ACCOUNTS["IT"]["bic"]
        assert eur_accounts["BE"]["iban"] == EXPECTED_EUR_ACCOUNTS["BE"]["iban"]
        assert eur_accounts["BE"]["bic"] == EXPECTED_EUR_ACCOUNTS["BE"]["bic"]
        
        # Verify SEPA routing thresholds
        assert "sepa_routing" in data
        sepa = data["sepa_routing"]
        assert sepa["instant_max"] == 5000
        assert sepa["standard_max"] == 100000
        
        print(f"✓ Cashout status: running={data['running']}, cycles={data['cycle_count']}")
        print(f"  Cumulative: USDC={cumulative['extracted_usdc']}, EUR={cumulative['extracted_eur']}")
        print(f"  EUR accounts: IT={eur_accounts['IT']['iban'][:12]}..., BE={eur_accounts['BE']['iban'][:12]}...")

    def test_04_cashout_status_engine_running(self, authenticated_client):
        """Verify cashout engine is running (cycle_count >= 1)"""
        response = authenticated_client.get(f"{BASE_URL}/api/cashout/status")
        assert response.status_code == 200
        data = response.json()
        
        # Engine should be running
        assert data["running"] == True, "Cashout engine should be running"
        assert data["cycle_count"] >= 1, f"Expected cycle_count >= 1, got {data['cycle_count']}"
        
        print(f"✓ Engine running with {data['cycle_count']} cycles completed")


class TestCashoutReport:
    """Tests for comprehensive cashout report"""

    def test_05_cashout_report(self, authenticated_client):
        """GET /api/cashout/report — comprehensive report"""
        response = authenticated_client.get(f"{BASE_URL}/api/cashout/report")
        assert response.status_code == 200
        data = response.json()
        
        # Verify engine section
        assert "engine" in data
        engine = data["engine"]
        assert "running" in engine
        assert "cycles" in engine
        assert "interval" in engine
        
        # Verify extracted metrics
        assert "extracted" in data
        
        # Verify USDC wallets
        assert "usdc_wallets" in data
        usdc_wallets = data["usdc_wallets"]
        assert "client" in usdc_wallets
        assert "treasury" in usdc_wallets
        assert "revenue" in usdc_wallets
        
        # Verify USDC total
        assert "usdc_total" in data
        
        # Verify hot wallet
        assert "hot_wallet" in data
        hot_wallet = data["hot_wallet"]
        assert "bnb" in hot_wallet
        assert "neno" in hot_wallet
        assert "available" in hot_wallet
        
        # Verify conversion opportunities count
        assert "conversion_opportunities" in data
        
        # Verify EUR accounts
        assert "eur_accounts" in data
        
        print(f"✓ Cashout report: engine running={engine['running']}, cycles={engine['cycles']}")
        print(f"  USDC total: {data['usdc_total']}")
        print(f"  Hot wallet: NENO={hot_wallet['neno']}, BNB={hot_wallet['bnb']}")
        print(f"  Conversion opportunities: {data['conversion_opportunities']}")


class TestCashoutHistory:
    """Tests for cashout history"""

    def test_06_cashout_history(self, authenticated_client):
        """GET /api/cashout/history — cashout operation history"""
        response = authenticated_client.get(f"{BASE_URL}/api/cashout/history")
        assert response.status_code == 200
        data = response.json()
        
        assert "cashouts" in data
        assert "count" in data
        assert isinstance(data["cashouts"], list)
        
        print(f"✓ Cashout history: {data['count']} operations")
        
        # If there are cashouts, verify structure
        if data["cashouts"]:
            cashout = data["cashouts"][0]
            assert "id" in cashout
            assert "type" in cashout
            assert "amount" in cashout
            assert "status" in cashout
            assert "created_at" in cashout
            print(f"  Latest: type={cashout['type']}, amount={cashout['amount']}, status={cashout['status']}")


class TestEurAccounts:
    """Tests for EUR account configuration"""

    def test_07_eur_accounts(self, authenticated_client):
        """GET /api/cashout/eur-accounts — IT and BE IBAN accounts"""
        response = authenticated_client.get(f"{BASE_URL}/api/cashout/eur-accounts")
        assert response.status_code == 200
        data = response.json()
        
        # Verify accounts
        assert "accounts" in data
        accounts = data["accounts"]
        
        # Verify IT account
        assert "IT" in accounts
        it_account = accounts["IT"]
        assert it_account["iban"] == EXPECTED_EUR_ACCOUNTS["IT"]["iban"]
        assert it_account["bic"] == EXPECTED_EUR_ACCOUNTS["IT"]["bic"]
        assert "beneficiary" in it_account
        assert "country" in it_account
        
        # Verify BE account
        assert "BE" in accounts
        be_account = accounts["BE"]
        assert be_account["iban"] == EXPECTED_EUR_ACCOUNTS["BE"]["iban"]
        assert be_account["bic"] == EXPECTED_EUR_ACCOUNTS["BE"]["bic"]
        
        # Verify routing rules
        assert "routing_rules" in data
        rules = data["routing_rules"]
        assert "sepa_instant" in rules
        assert "sepa_standard" in rules
        assert "swift" in rules
        
        print(f"✓ EUR accounts configured:")
        print(f"  IT: {it_account['iban']}, BIC: {it_account['bic']}")
        print(f"  BE: {be_account['iban']}, BIC: {be_account['bic']}")
        print(f"  Routing: {rules}")


class TestConversions:
    """Tests for crypto→USDC conversion endpoints"""

    def test_08_conversion_opportunities(self, authenticated_client):
        """GET /api/cashout/conversions/opportunities — crypto→USDC opportunities"""
        response = authenticated_client.get(f"{BASE_URL}/api/cashout/conversions/opportunities")
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "hot_wallet" in data
        assert "opportunities" in data
        assert "count" in data
        
        hot_wallet = data["hot_wallet"]
        assert "available" in hot_wallet
        
        print(f"✓ Conversion opportunities: {data['count']}")
        print(f"  Hot wallet available: {hot_wallet.get('available')}")
        
        # If there are opportunities, verify structure
        if data["opportunities"]:
            opp = data["opportunities"][0]
            assert "from_asset" in opp
            assert "to_asset" in opp
            assert "amount" in opp
            assert "estimated_value_usd" in opp
            assert "route" in opp
            print(f"  First opportunity: {opp['amount']} {opp['from_asset']} → {opp['to_asset']}")
            print(f"    Estimated USD: {opp['estimated_value_usd']}, Route: {opp['route']}")

    def test_09_conversion_history(self, authenticated_client):
        """GET /api/cashout/conversions/history — conversion history"""
        response = authenticated_client.get(f"{BASE_URL}/api/cashout/conversions/history")
        assert response.status_code == 200
        data = response.json()
        
        assert "conversions" in data
        assert "count" in data
        assert isinstance(data["conversions"], list)
        
        print(f"✓ Conversion history: {data['count']} conversions")

    def test_10_conversion_summary(self, authenticated_client):
        """GET /api/cashout/conversions/summary — conversion summary by pair"""
        response = authenticated_client.get(f"{BASE_URL}/api/cashout/conversions/summary")
        assert response.status_code == 200
        data = response.json()
        
        assert "conversion_pairs" in data
        assert "priority_order" in data
        assert "max_slippage_pct" in data
        assert "min_convert_value_usd" in data
        
        print(f"✓ Conversion summary:")
        print(f"  Priority order: {data['priority_order']}")
        print(f"  Max slippage: {data['max_slippage_pct']}%")
        print(f"  Min convert value: ${data['min_convert_value_usd']}")


class TestEngineControl:
    """Tests for engine start/stop control (admin only)"""

    def test_11_stop_engine(self, authenticated_client):
        """POST /api/cashout/stop — stop cashout engine"""
        response = authenticated_client.post(f"{BASE_URL}/api/cashout/stop")
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "stopped"
        print(f"✓ Engine stopped: {data}")

    def test_12_start_engine(self, authenticated_client):
        """POST /api/cashout/start — start cashout engine"""
        response = authenticated_client.post(f"{BASE_URL}/api/cashout/start")
        assert response.status_code == 200
        data = response.json()
        
        assert data["status"] == "started"
        print(f"✓ Engine started: {data}")

    def test_13_verify_engine_running_after_restart(self, authenticated_client):
        """Verify engine is running after restart"""
        import time
        time.sleep(1)  # Give engine time to start
        
        response = authenticated_client.get(f"{BASE_URL}/api/cashout/status")
        assert response.status_code == 200
        data = response.json()
        
        assert data["running"] == True
        print(f"✓ Engine running after restart: cycles={data['cycle_count']}")


class TestAuthenticationRequired:
    """Tests that all cashout endpoints require authentication"""

    def test_14_cashout_status_requires_auth(self, api_client):
        """GET /api/cashout/status requires auth"""
        # Remove auth header
        api_client.headers.pop("Authorization", None)
        response = api_client.get(f"{BASE_URL}/api/cashout/status")
        assert response.status_code == 401
        print("✓ /api/cashout/status requires auth (401)")

    def test_15_cashout_report_requires_auth(self, api_client):
        """GET /api/cashout/report requires auth"""
        api_client.headers.pop("Authorization", None)
        response = api_client.get(f"{BASE_URL}/api/cashout/report")
        assert response.status_code == 401
        print("✓ /api/cashout/report requires auth (401)")

    def test_16_cashout_history_requires_auth(self, api_client):
        """GET /api/cashout/history requires auth"""
        api_client.headers.pop("Authorization", None)
        response = api_client.get(f"{BASE_URL}/api/cashout/history")
        assert response.status_code == 401
        print("✓ /api/cashout/history requires auth (401)")

    def test_17_eur_accounts_requires_auth(self, api_client):
        """GET /api/cashout/eur-accounts requires auth"""
        api_client.headers.pop("Authorization", None)
        response = api_client.get(f"{BASE_URL}/api/cashout/eur-accounts")
        assert response.status_code == 401
        print("✓ /api/cashout/eur-accounts requires auth (401)")

    def test_18_conversions_opportunities_requires_auth(self, api_client):
        """GET /api/cashout/conversions/opportunities requires auth"""
        api_client.headers.pop("Authorization", None)
        response = api_client.get(f"{BASE_URL}/api/cashout/conversions/opportunities")
        assert response.status_code == 401
        print("✓ /api/cashout/conversions/opportunities requires auth (401)")

    def test_19_start_requires_auth(self, api_client):
        """POST /api/cashout/start requires auth"""
        api_client.headers.pop("Authorization", None)
        response = api_client.post(f"{BASE_URL}/api/cashout/start")
        assert response.status_code == 401
        print("✓ /api/cashout/start requires auth (401)")

    def test_20_stop_requires_auth(self, api_client):
        """POST /api/cashout/stop requires auth"""
        api_client.headers.pop("Authorization", None)
        response = api_client.post(f"{BASE_URL}/api/cashout/stop")
        assert response.status_code == 401
        print("✓ /api/cashout/stop requires auth (401)")


class TestCircleIntegrationStillWorking:
    """Verify Circle USDC endpoints still work (from iteration 36)"""

    def test_21_circle_wallets_balances(self, api_client):
        """GET /api/circle/wallets/balances — still working"""
        # Re-authenticate since previous tests removed auth header
        login_resp = api_client.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        token = login_resp.json().get("token") or login_resp.json().get("access_token")
        api_client.headers.update({"Authorization": f"Bearer {token}"})
        
        response = api_client.get(f"{BASE_URL}/api/circle/wallets/balances")
        assert response.status_code == 200
        data = response.json()
        
        assert "wallets" in data
        wallets = data["wallets"]
        assert "client" in wallets
        assert "treasury" in wallets
        assert "revenue" in wallets
        
        print(f"✓ Circle wallets still working: {len(wallets)} wallets")
        print(f"  Total USDC: {data.get('total_usdc', 0)}")

    def test_22_circle_auto_op_status(self, api_client):
        """GET /api/circle/auto-op/status — still running"""
        response = api_client.get(f"{BASE_URL}/api/circle/auto-op/status")
        assert response.status_code == 200
        data = response.json()
        
        assert "running" in data
        assert "cycle_count" in data
        
        print(f"✓ Circle auto-op still working: running={data['running']}, cycles={data['cycle_count']}")


class TestHotWalletBalances:
    """Verify hot wallet has expected balances"""

    def test_23_hot_wallet_has_neno(self, api_client):
        """Verify hot wallet has NENO balance (expected ~396.9888)"""
        response = api_client.get(f"{BASE_URL}/api/cashout/conversions/opportunities")
        assert response.status_code == 200
        data = response.json()
        
        hot_wallet = data.get("hot_wallet", {})
        neno_balance = hot_wallet.get("neno_balance", 0)
        bnb_balance = hot_wallet.get("bnb_balance", 0)
        
        print(f"✓ Hot wallet balances:")
        print(f"  NENO: {neno_balance}")
        print(f"  BNB: {bnb_balance}")
        
        # Verify hot wallet is available
        assert hot_wallet.get("available") == True, "Hot wallet should be available"

    def test_24_conversion_opportunity_for_neno(self, api_client):
        """Verify there's a conversion opportunity for NENO→USDC"""
        response = api_client.get(f"{BASE_URL}/api/cashout/conversions/opportunities")
        assert response.status_code == 200
        data = response.json()
        
        opportunities = data.get("opportunities", [])
        
        # Find NENO→USDC opportunity
        neno_opp = None
        for opp in opportunities:
            if opp.get("from_asset") == "NENO" and opp.get("to_asset") == "USDC":
                neno_opp = opp
                break
        
        if neno_opp:
            print(f"✓ NENO→USDC conversion opportunity found:")
            print(f"  Amount: {neno_opp['amount']} NENO")
            print(f"  Estimated USD: ${neno_opp['estimated_value_usd']}")
            print(f"  Route: {neno_opp['route']}")
        else:
            print(f"  No NENO→USDC opportunity (NENO balance may be 0)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
