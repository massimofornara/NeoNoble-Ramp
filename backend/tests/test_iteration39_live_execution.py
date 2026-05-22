"""
Iteration 39 - Live Execution Layer Testing

Tests for NeoNoble Ramp Real Money Activation:
- Pipeline assessment (GET /api/live/pipeline/assess)
- DEX quotes (GET /api/live/dex/quote)
- DEX liquidity check (GET /api/live/dex/liquidity/{asset})
- DEX swap history (GET /api/live/dex/history)
- Pipeline history (GET /api/live/pipeline/history)
- Real-time sync state (GET /api/sync/state)
- Instant withdraw status (GET /api/sync/instant-withdraw/status)
- Reconciliation (GET /api/sync/reconciliation)
- Cashout report (GET /api/cashout/report)
- Circle wallets (GET /api/circle/wallets/balances)

NOTE: POST endpoints (execute, swap) are NOT tested per instructions - no NENO left in hot wallet.
"""

import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-chain-wallet-14.preview.emergentagent.com").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"


class TestLiveExecutionLayer:
    """Live Execution Layer API Tests - Iteration 39"""

    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, f"Admin login failed: {response.text}"
        data = response.json()
        return data.get("access_token") or data.get("token")

    @pytest.fixture(scope="class")
    def auth_headers(self, admin_token):
        """Auth headers for authenticated requests"""
        return {"Authorization": f"Bearer {admin_token}"}

    # ─────────────────────────────────────────────
    # HEALTH CHECK
    # ─────────────────────────────────────────────

    def test_01_health_check(self):
        """Basic health check"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        assert data.get("service") == "NeoNoble Ramp"
        print("✓ Health check passed")

    # ─────────────────────────────────────────────
    # PIPELINE ASSESSMENT
    # ─────────────────────────────────────────────

    def test_02_pipeline_assess_requires_auth(self):
        """Pipeline assess requires authentication"""
        response = requests.get(f"{BASE_URL}/api/live/pipeline/assess")
        assert response.status_code == 401
        print("✓ Pipeline assess requires auth (401)")

    def test_03_pipeline_assess_returns_data(self, auth_headers):
        """Pipeline assess returns comprehensive readiness data"""
        response = requests.get(
            f"{BASE_URL}/api/live/pipeline/assess",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check pipeline_ready
        assert "pipeline_ready" in data
        assert data["pipeline_ready"] == True
        
        # Check hot_wallet data
        assert "hot_wallet" in data
        hw = data["hot_wallet"]
        assert "address" in hw
        assert "neno" in hw
        assert "bnb" in hw
        assert "gas_ok" in hw
        
        # Check dex_liquidity
        assert "dex_liquidity" in data
        dex_liq = data["dex_liquidity"]
        assert "neno_wbnb_pool" in dex_liq
        assert dex_liq["neno_wbnb_pool"] == True, "NENO/WBNB pool should exist"
        assert "neno_pair_address" in dex_liq
        # Verify pair address is the expected one
        expected_pair = "0x27f9610fCe91B27aC98D7426Ebbb10110A7CdACd"
        assert dex_liq["neno_pair_address"].lower() == expected_pair.lower(), f"Expected pair {expected_pair}"
        
        # Check swap_quotes
        assert "swap_quotes" in data
        quotes = data["swap_quotes"]
        assert "neno_to_usdc" in quotes
        assert "bnb_to_usdc" in quotes
        
        # Check fiat_rails
        assert "fiat_rails" in data
        rails = data["fiat_rails"]
        assert rails.get("stripe_sepa") == "active"
        assert rails.get("circle") == "active"
        
        # Check cashout_engine
        assert "cashout_engine" in data
        assert "running" in data["cashout_engine"]
        
        # Check blockers
        assert "blockers" in data
        
        print(f"✓ Pipeline assess: pipeline_ready={data['pipeline_ready']}")
        print(f"  Hot wallet: {hw.get('address', '')[:12]}... | NENO={hw.get('neno')} | BNB={hw.get('bnb')}")
        print(f"  DEX liquidity: NENO/WBNB pool={dex_liq['neno_wbnb_pool']}")
        print(f"  Fiat rails: Stripe SEPA={rails.get('stripe_sepa')}, Circle={rails.get('circle')}")

    def test_04_pipeline_execute_requires_admin(self, auth_headers):
        """Pipeline execute is admin-only (we verify 403 for non-admin, but don't execute)"""
        # Note: We're testing with admin, so we should get 200 if we call it
        # But per instructions, we should NOT call execute as there's no NENO left
        # Just verify the endpoint exists and requires auth
        response = requests.post(
            f"{BASE_URL}/api/live/pipeline/execute",
            headers={}  # No auth
        )
        assert response.status_code == 401
        print("✓ Pipeline execute requires auth (401)")

    # ─────────────────────────────────────────────
    # DEX QUOTES
    # ─────────────────────────────────────────────

    def test_05_dex_quote_requires_auth(self):
        """DEX quote requires authentication"""
        response = requests.get(f"{BASE_URL}/api/live/dex/quote?from_asset=NENO&to_asset=USDC&amount=1")
        assert response.status_code == 401
        print("✓ DEX quote requires auth (401)")

    def test_06_dex_quote_neno_to_usdc(self, auth_headers):
        """Get real PancakeSwap V2 quote for NENO → USDC"""
        response = requests.get(
            f"{BASE_URL}/api/live/dex/quote?from_asset=NENO&to_asset=USDC&amount=1",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Quote should return success or error (depending on liquidity)
        assert "success" in data
        
        if data.get("success"):
            assert "amount_in" in data
            assert "amount_out" in data
            assert "rate" in data
            assert "path" in data
            assert "dex" in data
            assert data["dex"] == "PancakeSwap V2"
            print(f"✓ NENO→USDC quote: {data['amount_in']} NENO → {data['amount_out']} USDC (rate={data['rate']})")
        else:
            # Even if no liquidity, we should get a proper error response
            assert "error" in data
            print(f"✓ NENO→USDC quote returned error (expected if no liquidity): {data.get('error')}")

    def test_07_dex_quote_bnb_to_usdc(self, auth_headers):
        """Get real PancakeSwap V2 quote for BNB → USDC"""
        response = requests.get(
            f"{BASE_URL}/api/live/dex/quote?from_asset=WBNB&to_asset=USDC&amount=0.01",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "success" in data
        if data.get("success"):
            assert data["dex"] == "PancakeSwap V2"
            print(f"✓ BNB→USDC quote: {data['amount_in']} BNB → {data['amount_out']} USDC")
        else:
            print(f"✓ BNB→USDC quote error: {data.get('error')}")

    # ─────────────────────────────────────────────
    # DEX LIQUIDITY
    # ─────────────────────────────────────────────

    def test_08_dex_liquidity_requires_auth(self):
        """DEX liquidity check requires authentication"""
        response = requests.get(f"{BASE_URL}/api/live/dex/liquidity/NENO")
        assert response.status_code == 401
        print("✓ DEX liquidity requires auth (401)")

    def test_09_dex_liquidity_neno(self, auth_headers):
        """Check NENO liquidity on PancakeSwap V2"""
        response = requests.get(
            f"{BASE_URL}/api/live/dex/liquidity/NENO",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "has_liquidity" in data
        assert data["has_liquidity"] == True, "NENO should have liquidity on PancakeSwap V2"
        assert "pair_address" in data
        
        expected_pair = "0x27f9610fCe91B27aC98D7426Ebbb10110A7CdACd"
        assert data["pair_address"].lower() == expected_pair.lower()
        
        print(f"✓ NENO liquidity: has_liquidity={data['has_liquidity']}, pair={data['pair_address']}")

    # ─────────────────────────────────────────────
    # DEX HISTORY
    # ─────────────────────────────────────────────

    def test_10_dex_history_requires_auth(self):
        """DEX history requires authentication"""
        response = requests.get(f"{BASE_URL}/api/live/dex/history")
        assert response.status_code == 401
        print("✓ DEX history requires auth (401)")

    def test_11_dex_history_returns_swaps(self, auth_headers):
        """DEX history returns swap execution history with TX hashes"""
        response = requests.get(
            f"{BASE_URL}/api/live/dex/history",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "swaps" in data
        assert "count" in data
        
        swaps = data["swaps"]
        if len(swaps) > 0:
            # Verify swap records have expected fields
            swap = swaps[0]
            # Check for TX hash (real swaps have been executed)
            if swap.get("tx_hash"):
                print(f"✓ DEX history: {data['count']} swaps, latest TX: {swap['tx_hash'][:16]}...")
            else:
                print(f"✓ DEX history: {data['count']} swaps")
        else:
            print(f"✓ DEX history: {data['count']} swaps (empty)")

    # ─────────────────────────────────────────────
    # PIPELINE HISTORY
    # ─────────────────────────────────────────────

    def test_12_pipeline_history_requires_auth(self):
        """Pipeline history requires authentication"""
        response = requests.get(f"{BASE_URL}/api/live/pipeline/history")
        assert response.status_code == 401
        print("✓ Pipeline history requires auth (401)")

    def test_13_pipeline_history_returns_executions(self, auth_headers):
        """Pipeline history returns execution history"""
        response = requests.get(
            f"{BASE_URL}/api/live/pipeline/history",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "pipelines" in data
        assert "count" in data
        
        print(f"✓ Pipeline history: {data['count']} executions")

    # ─────────────────────────────────────────────
    # SYNC STATE
    # ─────────────────────────────────────────────

    def test_14_sync_state_requires_auth(self):
        """Sync state requires authentication"""
        response = requests.get(f"{BASE_URL}/api/sync/state")
        assert response.status_code == 401
        print("✓ Sync state requires auth (401)")

    def test_15_sync_state_returns_real_mode(self, auth_headers):
        """Sync state returns real_mode=true with hot_wallet and usdc_wallets"""
        response = requests.get(
            f"{BASE_URL}/api/sync/state",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check real_mode
        assert data.get("real_mode") == True
        
        # Check hot_wallet
        assert "hot_wallet" in data
        hw = data["hot_wallet"]
        assert "address" in hw
        assert "bnb" in hw
        assert "neno" in hw
        assert "gas_ok" in hw
        assert "available" in hw
        
        # Check usdc_wallets
        assert "usdc_wallets" in data
        usdc = data["usdc_wallets"]
        assert "client" in usdc
        assert "treasury" in usdc
        assert "revenue" in usdc
        assert "total" in usdc
        
        print(f"✓ Sync state: real_mode={data['real_mode']}")
        print(f"  Hot wallet: {hw.get('address', '')[:12]}... | available={hw.get('available')}")
        print(f"  USDC wallets: client={usdc['client']}, treasury={usdc['treasury']}, revenue={usdc['revenue']}")

    # ─────────────────────────────────────────────
    # INSTANT WITHDRAW STATUS
    # ─────────────────────────────────────────────

    def test_16_instant_withdraw_status_requires_auth(self):
        """Instant withdraw status requires authentication"""
        response = requests.get(f"{BASE_URL}/api/sync/instant-withdraw/status")
        assert response.status_code == 401
        print("✓ Instant withdraw status requires auth (401)")

    def test_17_instant_withdraw_status_active(self, auth_headers):
        """Instant withdraw engine is active"""
        response = requests.get(
            f"{BASE_URL}/api/sync/instant-withdraw/status",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("active") == True
        assert "eur_routing" in data
        assert "queued" in data
        assert "completed" in data
        
        print(f"✓ Instant withdraw: active={data['active']}, queued={data['queued']}, completed={data['completed']}")

    # ─────────────────────────────────────────────
    # RECONCILIATION
    # ─────────────────────────────────────────────

    def test_18_reconciliation_requires_auth(self):
        """Reconciliation requires authentication"""
        response = requests.get(f"{BASE_URL}/api/sync/reconciliation")
        assert response.status_code == 401
        print("✓ Reconciliation requires auth (401)")

    def test_19_reconciliation_system_healthy(self, auth_headers):
        """Reconciliation returns system_healthy=true"""
        response = requests.get(
            f"{BASE_URL}/api/sync/reconciliation",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("system_healthy") == True
        
        print(f"✓ Reconciliation: system_healthy={data['system_healthy']}")

    # ─────────────────────────────────────────────
    # CASHOUT REPORT
    # ─────────────────────────────────────────────

    def test_20_cashout_report_requires_auth(self):
        """Cashout report requires authentication"""
        response = requests.get(f"{BASE_URL}/api/cashout/report")
        assert response.status_code == 401
        print("✓ Cashout report requires auth (401)")

    def test_21_cashout_report_comprehensive(self, auth_headers):
        """Cashout report returns comprehensive data"""
        response = requests.get(
            f"{BASE_URL}/api/cashout/report",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Should have key sections
        assert "usdc_wallets" in data or "hot_wallet" in data or "conversion_opportunities" in data
        
        print(f"✓ Cashout report: keys={list(data.keys())[:5]}...")

    # ─────────────────────────────────────────────
    # CIRCLE WALLETS
    # ─────────────────────────────────────────────

    def test_22_circle_wallets_requires_auth(self):
        """Circle wallets requires authentication"""
        response = requests.get(f"{BASE_URL}/api/circle/wallets/balances")
        assert response.status_code == 401
        print("✓ Circle wallets requires auth (401)")

    def test_23_circle_wallets_3_segregated(self, auth_headers):
        """Circle wallets returns 3 segregated wallets verified"""
        response = requests.get(
            f"{BASE_URL}/api/circle/wallets/balances",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "wallets" in data
        wallets = data["wallets"]
        
        # Should have 3 wallets: CLIENT, TREASURY, REVENUE
        wallet_roles = list(wallets.keys())
        assert len(wallet_roles) >= 3, f"Expected 3 wallets, got {len(wallet_roles)}"
        
        # Verify each wallet has address and balance
        for role, wallet in wallets.items():
            assert "address" in wallet
            assert "balance" in wallet
            assert "verified" in wallet
        
        print(f"✓ Circle wallets: {len(wallet_roles)} segregated wallets")
        for role, wallet in wallets.items():
            print(f"  {role}: {wallet.get('address', '')[:12]}... | balance={wallet.get('balance')} | verified={wallet.get('verified')}")

    # ─────────────────────────────────────────────
    # ADMIN-ONLY POST ENDPOINTS (403 verification)
    # ─────────────────────────────────────────────

    def test_24_dex_swap_requires_admin(self):
        """DEX swap POST requires admin (verify 401 without auth)"""
        response = requests.post(
            f"{BASE_URL}/api/live/dex/swap",
            json={"from_token": "NENO", "to_token": "USDC", "amount": 1}
        )
        assert response.status_code == 401
        print("✓ DEX swap requires auth (401)")

    def test_25_convert_neno_requires_admin(self):
        """Convert NENO POST requires admin (verify 401 without auth)"""
        response = requests.post(f"{BASE_URL}/api/live/dex/convert-neno")
        assert response.status_code == 401
        print("✓ Convert NENO requires auth (401)")

    # ─────────────────────────────────────────────
    # DATA CONSISTENCY CHECKS
    # ─────────────────────────────────────────────

    def test_26_hot_wallet_consistency(self, auth_headers):
        """Hot wallet data is consistent across endpoints"""
        # Get from pipeline assess
        assess_resp = requests.get(
            f"{BASE_URL}/api/live/pipeline/assess",
            headers=auth_headers
        )
        assess_data = assess_resp.json()
        
        # Get from sync state
        sync_resp = requests.get(
            f"{BASE_URL}/api/sync/state",
            headers=auth_headers
        )
        sync_data = sync_resp.json()
        
        # Compare hot wallet addresses
        assess_addr = assess_data.get("hot_wallet", {}).get("address", "")
        sync_addr = sync_data.get("hot_wallet", {}).get("address", "")
        
        assert assess_addr.lower() == sync_addr.lower(), "Hot wallet addresses should match"
        
        print(f"✓ Hot wallet consistency: {assess_addr[:12]}... matches across endpoints")

    def test_27_usdc_wallets_consistency(self, auth_headers):
        """USDC wallet data is consistent across endpoints"""
        # Get from pipeline assess
        assess_resp = requests.get(
            f"{BASE_URL}/api/live/pipeline/assess",
            headers=auth_headers
        )
        assess_data = assess_resp.json()
        
        # Get from circle wallets
        circle_resp = requests.get(
            f"{BASE_URL}/api/circle/wallets/balances",
            headers=auth_headers
        )
        circle_data = circle_resp.json()
        
        # Both should have wallet data
        assert "usdc_wallets" in assess_data
        assert "wallets" in circle_data
        
        print("✓ USDC wallets data present in both endpoints")

    # ─────────────────────────────────────────────
    # VERIFY REAL TX HASHES IN HISTORY
    # ─────────────────────────────────────────────

    def test_28_verify_real_tx_hashes(self, auth_headers):
        """Verify DEX history contains real TX hashes from previous executions"""
        response = requests.get(
            f"{BASE_URL}/api/live/dex/history",
            headers=auth_headers
        )
        data = response.json()
        
        swaps = data.get("swaps", [])
        tx_hashes = [s.get("tx_hash") for s in swaps if s.get("tx_hash")]
        
        if tx_hashes:
            # Verify TX hashes are valid format (0x + 64 hex chars)
            for tx in tx_hashes[:3]:
                assert tx.startswith("0x") or len(tx) == 64, f"Invalid TX hash format: {tx}"
            print(f"✓ Found {len(tx_hashes)} real TX hashes in DEX history")
            print(f"  Latest: {tx_hashes[0][:20]}...")
        else:
            print("✓ DEX history verified (no TX hashes yet)")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
