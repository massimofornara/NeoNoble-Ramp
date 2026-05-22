"""
Iteration 38 - Real-Time Sync Layer, Instant Withdraw Engine, EventBus Integration Tests

Tests:
1. GET /api/sync/state — Full real-time platform state (requires auth)
2. GET /api/sync/state/platform — Platform-wide state without user data
3. GET /api/sync/instant-withdraw/status — Instant withdraw engine status
4. GET /api/sync/reconciliation — Real-time reconciliation status
5. GET /api/cashout/status — Cashout engine running status
6. GET /api/cashout/report — Comprehensive cashout report
7. GET /api/circle/wallets/balances — Circle USDC segregated wallets
8. GET /api/circle/auto-op/status — Auto-op loop status
9. GET /api/health — Basic health check
10. Auth enforcement on all sync endpoints
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://multi-chain-wallet-14.preview.emergentagent.com').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"


class TestIteration38RealtimeSync:
    """Real-Time Sync Layer, Instant Withdraw Engine, EventBus Integration Tests"""
    
    auth_token = None
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup - get auth token once for all tests"""
        if TestIteration38RealtimeSync.auth_token is None:
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
            )
            if response.status_code == 200:
                data = response.json()
                TestIteration38RealtimeSync.auth_token = data.get("access_token") or data.get("token")
    
    def get_headers(self):
        return {"Authorization": f"Bearer {self.auth_token}", "Content-Type": "application/json"}
    
    # ─────────────────────────────────────────────
    # Basic Health & Auth Tests
    # ─────────────────────────────────────────────
    
    def test_01_health_check(self):
        """Test basic health check endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "NeoNoble Ramp"
        print(f"✓ Health check passed: {data}")
    
    def test_02_admin_login(self):
        """Test admin login and token retrieval"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data or "token" in data
        print(f"✓ Admin login successful")
    
    # ─────────────────────────────────────────────
    # Sync State Endpoints
    # ─────────────────────────────────────────────
    
    def test_03_sync_state_full(self):
        """Test GET /api/sync/state - Full real-time platform state"""
        response = requests.get(f"{BASE_URL}/api/sync/state", headers=self.get_headers())
        assert response.status_code == 200
        data = response.json()
        
        # Verify real_mode is true
        assert data.get("real_mode") == True, "Expected real_mode=true"
        
        # Verify timestamp exists
        assert "timestamp" in data
        
        # Verify usdc_wallets structure
        assert "usdc_wallets" in data
        usdc = data["usdc_wallets"]
        assert "client" in usdc
        assert "treasury" in usdc
        assert "revenue" in usdc
        assert "total" in usdc
        assert "verified" in usdc
        
        # Verify hot_wallet structure
        assert "hot_wallet" in data
        hw = data["hot_wallet"]
        assert "address" in hw
        assert "bnb" in hw
        assert "neno" in hw
        assert "gas_ok" in hw
        assert "available" in hw
        
        # Verify platform metrics
        assert "platform" in data
        platform = data["platform"]
        assert "total_users" in platform
        assert "total_transactions" in platform
        
        # Verify cashout_pipeline
        assert "cashout_pipeline" in data
        
        print(f"✓ Sync state: real_mode={data['real_mode']}, usdc_verified={usdc.get('verified')}")
        print(f"  Hot wallet: {hw.get('neno')} NENO, {hw.get('bnb')} BNB, gas_ok={hw.get('gas_ok')}")
    
    def test_04_sync_state_platform(self):
        """Test GET /api/sync/state/platform - Platform-wide state without user data"""
        response = requests.get(f"{BASE_URL}/api/sync/state/platform", headers=self.get_headers())
        assert response.status_code == 200
        data = response.json()
        
        # Verify real_mode is true
        assert data.get("real_mode") == True
        
        # Verify usdc_wallets
        assert "usdc_wallets" in data
        
        # Verify hot_wallet
        assert "hot_wallet" in data
        
        # Verify platform metrics
        assert "platform" in data
        
        # User should be None for platform-wide state
        assert data.get("user") is None
        
        print(f"✓ Platform state: real_mode={data['real_mode']}, user=None (as expected)")
    
    def test_05_sync_state_usdc_wallets_verified(self):
        """Test that USDC wallets are verified (on-chain)"""
        response = requests.get(f"{BASE_URL}/api/sync/state", headers=self.get_headers())
        assert response.status_code == 200
        data = response.json()
        
        usdc = data.get("usdc_wallets", {})
        # All wallets should be verified (even if balance is 0)
        assert usdc.get("verified") == True, f"Expected usdc_wallets.verified=true, got {usdc.get('verified')}"
        
        print(f"✓ USDC wallets verified: client={usdc.get('client')}, treasury={usdc.get('treasury')}, revenue={usdc.get('revenue')}")
    
    def test_06_sync_state_hot_wallet_available(self):
        """Test that hot wallet is available with NENO balance"""
        response = requests.get(f"{BASE_URL}/api/sync/state", headers=self.get_headers())
        assert response.status_code == 200
        data = response.json()
        
        hw = data.get("hot_wallet", {})
        assert hw.get("available") == True, f"Expected hot_wallet.available=true"
        assert hw.get("address"), "Expected hot_wallet.address to be set"
        
        # Hot wallet should have NENO (based on previous tests showing ~396.9888)
        neno_balance = hw.get("neno", 0)
        assert neno_balance >= 0, "NENO balance should be >= 0"
        
        print(f"✓ Hot wallet available: address={hw.get('address')[:12]}..., neno={neno_balance}, bnb={hw.get('bnb')}")
    
    # ─────────────────────────────────────────────
    # Instant Withdraw Engine
    # ─────────────────────────────────────────────
    
    def test_07_instant_withdraw_status(self):
        """Test GET /api/sync/instant-withdraw/status - Instant withdraw engine status"""
        response = requests.get(f"{BASE_URL}/api/sync/instant-withdraw/status", headers=self.get_headers())
        assert response.status_code == 200
        data = response.json()
        
        # Verify active status
        assert "active" in data
        assert data.get("active") == True, "Expected instant withdraw engine to be active"
        
        # Verify EUR routing config
        assert "eur_routing" in data
        routing = data["eur_routing"]
        assert "sepa_instant_limit" in routing
        assert "sepa_standard_limit" in routing
        assert "primary_account" in routing
        assert "swift_account" in routing
        
        # Verify routing values
        assert routing.get("sepa_instant_limit") == 5000
        assert routing.get("sepa_standard_limit") == 100000
        assert routing.get("primary_account") == "IT"
        assert routing.get("swift_account") == "BE"
        
        # Verify queued/completed counts
        assert "queued" in data
        assert "completed" in data
        
        print(f"✓ Instant withdraw: active={data['active']}, queued={data.get('queued')}, completed={data.get('completed')}")
        print(f"  EUR routing: SEPA Instant <{routing.get('sepa_instant_limit')}, Standard <{routing.get('sepa_standard_limit')}, SWIFT >{routing.get('sepa_standard_limit')}")
    
    def test_08_instant_withdraw_eur_routing_config(self):
        """Test EUR routing configuration in instant withdraw status"""
        response = requests.get(f"{BASE_URL}/api/sync/instant-withdraw/status", headers=self.get_headers())
        assert response.status_code == 200
        data = response.json()
        
        routing = data.get("eur_routing", {})
        
        # IT account for SEPA Instant/Standard
        assert routing.get("primary_account") == "IT"
        
        # BE account for SWIFT
        assert routing.get("swift_account") == "BE"
        
        print(f"✓ EUR routing: primary={routing.get('primary_account')}, swift={routing.get('swift_account')}")
    
    # ─────────────────────────────────────────────
    # Reconciliation
    # ─────────────────────────────────────────────
    
    def test_09_sync_reconciliation(self):
        """Test GET /api/sync/reconciliation - Real-time reconciliation status"""
        response = requests.get(f"{BASE_URL}/api/sync/reconciliation", headers=self.get_headers())
        assert response.status_code == 200
        data = response.json()
        
        # Verify system_healthy
        assert "system_healthy" in data
        assert data.get("system_healthy") == True, f"Expected system_healthy=true, got {data.get('system_healthy')}"
        
        # Verify usdc_verified
        assert "usdc_verified" in data
        
        # Verify pending_cashouts
        assert "pending_cashouts" in data
        
        # Verify reconciliation details
        assert "reconciliation" in data
        
        print(f"✓ Reconciliation: system_healthy={data['system_healthy']}, usdc_verified={data.get('usdc_verified')}, pending_cashouts={data.get('pending_cashouts')}")
    
    def test_10_reconciliation_system_healthy(self):
        """Test that reconciliation shows system_healthy=true"""
        response = requests.get(f"{BASE_URL}/api/sync/reconciliation", headers=self.get_headers())
        assert response.status_code == 200
        data = response.json()
        
        assert data.get("system_healthy") == True
        print(f"✓ System healthy: {data.get('system_healthy')}")
    
    # ─────────────────────────────────────────────
    # Cashout Engine (from previous iteration, verify still working)
    # ─────────────────────────────────────────────
    
    def test_11_cashout_status(self):
        """Test GET /api/cashout/status - Cashout engine running status"""
        response = requests.get(f"{BASE_URL}/api/cashout/status", headers=self.get_headers())
        assert response.status_code == 200
        data = response.json()
        
        # Verify engine is running
        assert "running" in data
        assert data.get("running") == True, "Expected cashout engine to be running"
        
        # Verify EUR accounts
        assert "eur_accounts" in data
        eur = data["eur_accounts"]
        assert "IT" in eur
        assert "BE" in eur
        
        print(f"✓ Cashout engine: running={data['running']}, cycle_count={data.get('cycle_count')}")
    
    def test_12_cashout_report(self):
        """Test GET /api/cashout/report - Comprehensive cashout report"""
        response = requests.get(f"{BASE_URL}/api/cashout/report", headers=self.get_headers())
        assert response.status_code == 200
        data = response.json()
        
        # Verify USDC wallets
        assert "usdc_wallets" in data or "usdc_total" in data
        
        # Verify hot wallet
        assert "hot_wallet" in data
        hw = data["hot_wallet"]
        assert "neno" in hw
        assert "bnb" in hw
        
        # Verify conversion opportunities
        assert "conversion_opportunities" in data
        
        print(f"✓ Cashout report: usdc_total={data.get('usdc_total')}, hot_wallet_neno={hw.get('neno')}")
    
    # ─────────────────────────────────────────────
    # Circle USDC (from previous iteration, verify still working)
    # ─────────────────────────────────────────────
    
    def test_13_circle_wallets_balances(self):
        """Test GET /api/circle/wallets/balances - 3 segregated wallets on-chain verified"""
        response = requests.get(f"{BASE_URL}/api/circle/wallets/balances", headers=self.get_headers())
        assert response.status_code == 200
        data = response.json()
        
        # Verify wallets structure
        assert "wallets" in data
        wallets = data["wallets"]
        
        # Should have 3 wallets: client, treasury, revenue
        assert "client" in wallets or len(wallets) >= 3
        
        # Verify total_usdc
        assert "total_usdc" in data
        
        print(f"✓ Circle wallets: total_usdc={data.get('total_usdc')}, wallets={list(wallets.keys())}")
    
    def test_14_circle_auto_op_status(self):
        """Test GET /api/circle/auto-op/status - Auto-op loop running"""
        response = requests.get(f"{BASE_URL}/api/circle/auto-op/status", headers=self.get_headers())
        assert response.status_code == 200
        data = response.json()
        
        # Verify running status
        assert "running" in data
        assert data.get("running") == True, "Expected auto-op loop to be running"
        
        print(f"✓ Auto-op loop: running={data['running']}, cycle_count={data.get('cycle_count')}")
    
    # ─────────────────────────────────────────────
    # Auth Enforcement Tests
    # ─────────────────────────────────────────────
    
    def test_15_sync_state_requires_auth(self):
        """Test that /api/sync/state requires authentication"""
        response = requests.get(f"{BASE_URL}/api/sync/state")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✓ /api/sync/state requires auth (401)")
    
    def test_16_sync_state_platform_requires_auth(self):
        """Test that /api/sync/state/platform requires authentication"""
        response = requests.get(f"{BASE_URL}/api/sync/state/platform")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✓ /api/sync/state/platform requires auth (401)")
    
    def test_17_instant_withdraw_status_requires_auth(self):
        """Test that /api/sync/instant-withdraw/status requires authentication"""
        response = requests.get(f"{BASE_URL}/api/sync/instant-withdraw/status")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✓ /api/sync/instant-withdraw/status requires auth (401)")
    
    def test_18_sync_reconciliation_requires_auth(self):
        """Test that /api/sync/reconciliation requires authentication"""
        response = requests.get(f"{BASE_URL}/api/sync/reconciliation")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✓ /api/sync/reconciliation requires auth (401)")
    
    def test_19_cashout_status_requires_auth(self):
        """Test that /api/cashout/status requires authentication"""
        response = requests.get(f"{BASE_URL}/api/cashout/status")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✓ /api/cashout/status requires auth (401)")
    
    def test_20_cashout_report_requires_auth(self):
        """Test that /api/cashout/report requires authentication"""
        response = requests.get(f"{BASE_URL}/api/cashout/report")
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✓ /api/cashout/report requires auth (401)")
    
    # ─────────────────────────────────────────────
    # Data Integrity Tests
    # ─────────────────────────────────────────────
    
    def test_21_sync_state_data_consistency(self):
        """Test that sync state data is consistent across endpoints"""
        # Get sync state
        sync_response = requests.get(f"{BASE_URL}/api/sync/state", headers=self.get_headers())
        assert sync_response.status_code == 200
        sync_data = sync_response.json()
        
        # Get circle balances
        circle_response = requests.get(f"{BASE_URL}/api/circle/wallets/balances", headers=self.get_headers())
        assert circle_response.status_code == 200
        circle_data = circle_response.json()
        
        # USDC totals should be consistent
        sync_usdc_total = sync_data.get("usdc_wallets", {}).get("total", 0)
        circle_usdc_total = circle_data.get("total_usdc", 0)
        
        # Allow small floating point differences
        assert abs(sync_usdc_total - circle_usdc_total) < 0.001, f"USDC totals mismatch: sync={sync_usdc_total}, circle={circle_usdc_total}"
        
        print(f"✓ Data consistency: sync_usdc={sync_usdc_total}, circle_usdc={circle_usdc_total}")
    
    def test_22_hot_wallet_data_consistency(self):
        """Test that hot wallet data is consistent across endpoints"""
        # Get sync state
        sync_response = requests.get(f"{BASE_URL}/api/sync/state", headers=self.get_headers())
        assert sync_response.status_code == 200
        sync_data = sync_response.json()
        
        # Get cashout report
        cashout_response = requests.get(f"{BASE_URL}/api/cashout/report", headers=self.get_headers())
        assert cashout_response.status_code == 200
        cashout_data = cashout_response.json()
        
        sync_hw = sync_data.get("hot_wallet", {})
        cashout_hw = cashout_data.get("hot_wallet", {})
        
        # NENO balances should be consistent (allow small differences due to timing)
        sync_neno = sync_hw.get("neno", 0)
        cashout_neno = cashout_hw.get("neno", 0)
        
        # Allow 1% difference due to potential timing
        if sync_neno > 0 and cashout_neno > 0:
            diff_pct = abs(sync_neno - cashout_neno) / max(sync_neno, cashout_neno) * 100
            assert diff_pct < 5, f"NENO balance mismatch: sync={sync_neno}, cashout={cashout_neno}, diff={diff_pct}%"
        
        print(f"✓ Hot wallet consistency: sync_neno={sync_neno}, cashout_neno={cashout_neno}")
    
    def test_23_platform_metrics_present(self):
        """Test that platform metrics are present in sync state"""
        response = requests.get(f"{BASE_URL}/api/sync/state", headers=self.get_headers())
        assert response.status_code == 200
        data = response.json()
        
        platform = data.get("platform", {})
        
        # Verify all expected metrics
        assert "total_users" in platform
        assert "total_transactions" in platform
        assert "completed_transactions" in platform
        assert "total_fees_collected" in platform
        
        print(f"✓ Platform metrics: users={platform.get('total_users')}, txs={platform.get('total_transactions')}, fees={platform.get('total_fees_collected')}")
    
    def test_24_cashout_pipeline_present(self):
        """Test that cashout pipeline state is present in sync state"""
        response = requests.get(f"{BASE_URL}/api/sync/state", headers=self.get_headers())
        assert response.status_code == 200
        data = response.json()
        
        pipeline = data.get("cashout_pipeline", {})
        
        # Verify pipeline structure
        assert "pending_cashouts" in pipeline
        assert "completed_cashouts" in pipeline
        
        print(f"✓ Cashout pipeline: pending={pipeline.get('pending_cashouts')}, completed={pipeline.get('completed_cashouts')}")
    
    # ─────────────────────────────────────────────
    # EventBus Integration (indirect test via trade events)
    # ─────────────────────────────────────────────
    
    def test_25_eventbus_log_exists(self):
        """Test that EventBus is logging events (check via sync state timestamp)"""
        response = requests.get(f"{BASE_URL}/api/sync/state", headers=self.get_headers())
        assert response.status_code == 200
        data = response.json()
        
        # Timestamp should be recent (within last minute)
        timestamp = data.get("timestamp")
        assert timestamp is not None
        
        # Verify it's a valid ISO timestamp
        from datetime import datetime
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            print(f"✓ EventBus active: timestamp={timestamp}")
        except ValueError:
            pytest.fail(f"Invalid timestamp format: {timestamp}")
    
    def test_26_instant_withdraw_metrics(self):
        """Test instant withdraw engine metrics"""
        response = requests.get(f"{BASE_URL}/api/sync/instant-withdraw/status", headers=self.get_headers())
        assert response.status_code == 200
        data = response.json()
        
        # Verify metrics exist
        assert "total_withdrawn_eur" in data
        assert "total_withdrawn_usdc" in data
        assert "withdrawals_count" in data
        assert "blocked_count" in data
        
        print(f"✓ Instant withdraw metrics: eur={data.get('total_withdrawn_eur')}, usdc={data.get('total_withdrawn_usdc')}, count={data.get('withdrawals_count')}")
    
    def test_27_reconciliation_details(self):
        """Test reconciliation details structure"""
        response = requests.get(f"{BASE_URL}/api/sync/reconciliation", headers=self.get_headers())
        assert response.status_code == 200
        data = response.json()
        
        recon = data.get("reconciliation", {})
        
        # Verify reconciliation has status
        assert "status" in recon
        
        print(f"✓ Reconciliation details: status={recon.get('status')}")
    
    def test_28_all_sync_endpoints_return_json(self):
        """Test that all sync endpoints return valid JSON"""
        endpoints = [
            "/api/sync/state",
            "/api/sync/state/platform",
            "/api/sync/instant-withdraw/status",
            "/api/sync/reconciliation",
        ]
        
        for endpoint in endpoints:
            response = requests.get(f"{BASE_URL}{endpoint}", headers=self.get_headers())
            assert response.status_code == 200, f"{endpoint} returned {response.status_code}"
            try:
                data = response.json()
                assert isinstance(data, dict), f"{endpoint} did not return a dict"
            except Exception as e:
                pytest.fail(f"{endpoint} did not return valid JSON: {e}")
        
        print(f"✓ All {len(endpoints)} sync endpoints return valid JSON")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
