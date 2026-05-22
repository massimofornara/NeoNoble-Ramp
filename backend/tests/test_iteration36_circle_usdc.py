"""
Iteration 36 - Circle USDC Programmable Wallets Integration Tests

Tests for:
- GET /api/circle/wallets/balances — 3 segregated wallet on-chain USDC balances
- GET /api/circle/wallets/{role}/balance — single wallet balance (client, treasury, revenue)
- GET /api/circle/diagnostic — Circle API health check
- GET /api/circle/segregation/summary — wallet segregation movement summary
- GET /api/circle/segregation/reconciliation — on-chain vs ledger reconciliation
- GET /api/circle/segregation/movements — list of wallet movements
- POST /api/circle/segregation/move — admin-only manual rebalance
- GET /api/circle/auto-op/status — auto-operation loop status
- POST /api/circle/auto-op/start — start auto-op loop (admin only)
- POST /api/circle/auto-op/stop — stop auto-op loop (admin only)
- GET /api/circle/fail-safe/report — fail-safe reality check
- GET /api/strategic/real-treasury — existing real treasury endpoint
- GET /api/health — basic health check
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Module-level session to avoid rate limiting
_auth_session = None
_auth_token = None

def get_auth_session():
    """Get or create authenticated session (singleton to avoid rate limiting)"""
    global _auth_session, _auth_token
    
    if _auth_session is not None and _auth_token is not None:
        return _auth_session, _auth_token
    
    _auth_session = requests.Session()
    _auth_session.headers.update({'Content-Type': 'application/json'})
    
    # Login to get token
    login_resp = _auth_session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@neonobleramp.com",
        "password": "Admin1234!"
    })
    
    if login_resp.status_code == 429:
        # Rate limited, wait and retry
        retry_after = login_resp.json().get('retry_after', 30)
        print(f"Rate limited, waiting {retry_after}s...")
        time.sleep(retry_after + 1)
        login_resp = _auth_session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@neonobleramp.com",
            "password": "Admin1234!"
        })
    
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    _auth_token = login_resp.json().get('token')
    assert _auth_token, "No token in login response"
    _auth_session.headers.update({'Authorization': f'Bearer {_auth_token}'})
    
    return _auth_session, _auth_token


class TestCircleUSDCIntegration:
    """Circle USDC Programmable Wallets API tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup auth token for all tests (uses singleton session)"""
        self.session, self.token = get_auth_session()
    
    # ─────────────────────────────────────────────
    # HEALTH CHECK
    # ─────────────────────────────────────────────
    
    def test_01_health_check(self):
        """GET /api/health returns healthy status"""
        resp = self.session.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get('status') == 'healthy'
        assert data.get('service') == 'NeoNoble Ramp'
        print(f"✓ Health check passed: {data}")
    
    # ─────────────────────────────────────────────
    # WALLET BALANCES
    # ─────────────────────────────────────────────
    
    def test_02_get_all_wallet_balances(self):
        """GET /api/circle/wallets/balances returns 3 segregated wallets with verified=true"""
        resp = self.session.get(f"{BASE_URL}/api/circle/wallets/balances")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        # Check structure
        assert 'wallets' in data, "Missing 'wallets' key"
        assert 'total_usdc' in data, "Missing 'total_usdc' key"
        assert 'chain' in data, "Missing 'chain' key"
        assert 'verified_at' in data, "Missing 'verified_at' key"
        
        # Check all 3 wallet roles exist
        wallets = data['wallets']
        assert 'client' in wallets, "Missing 'client' wallet"
        assert 'treasury' in wallets, "Missing 'treasury' wallet"
        assert 'revenue' in wallets, "Missing 'revenue' wallet"
        
        # Check each wallet has required fields and verified=true
        for role in ['client', 'treasury', 'revenue']:
            wallet = wallets[role]
            assert 'address' in wallet, f"Missing 'address' for {role}"
            assert 'balance' in wallet, f"Missing 'balance' for {role}"
            assert 'verified' in wallet, f"Missing 'verified' for {role}"
            assert wallet['verified'] == True, f"Wallet {role} not verified on-chain"
            assert 'role' in wallet, f"Missing 'role' for {role}"
            assert wallet['role'] == role, f"Role mismatch for {role}"
        
        print(f"✓ All 3 wallets verified on-chain:")
        for role, w in wallets.items():
            print(f"  {role}: {w['balance']} USDC @ {w['address'][:20]}...")
        print(f"  Total: {data['total_usdc']} USDC on {data['chain']}")
    
    def test_03_get_client_wallet_balance(self):
        """GET /api/circle/wallets/client/balance returns client wallet balance"""
        resp = self.session.get(f"{BASE_URL}/api/circle/wallets/client/balance")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get('role') == 'client'
        assert 'address' in data
        assert 'balance' in data
        assert data.get('verified') == True
        print(f"✓ Client wallet: {data['balance']} USDC, verified={data['verified']}")
    
    def test_04_get_treasury_wallet_balance(self):
        """GET /api/circle/wallets/treasury/balance returns treasury wallet balance"""
        resp = self.session.get(f"{BASE_URL}/api/circle/wallets/treasury/balance")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get('role') == 'treasury'
        assert 'address' in data
        assert 'balance' in data
        assert data.get('verified') == True
        print(f"✓ Treasury wallet: {data['balance']} USDC, verified={data['verified']}")
    
    def test_05_get_revenue_wallet_balance(self):
        """GET /api/circle/wallets/revenue/balance returns revenue wallet balance"""
        resp = self.session.get(f"{BASE_URL}/api/circle/wallets/revenue/balance")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert data.get('role') == 'revenue'
        assert 'address' in data
        assert 'balance' in data
        assert data.get('verified') == True
        print(f"✓ Revenue wallet: {data['balance']} USDC, verified={data['verified']}")
    
    def test_06_invalid_wallet_role_returns_400(self):
        """GET /api/circle/wallets/invalid/balance returns 400"""
        resp = self.session.get(f"{BASE_URL}/api/circle/wallets/invalid/balance")
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
        print(f"✓ Invalid wallet role correctly returns 400")
    
    # ─────────────────────────────────────────────
    # DIAGNOSTIC
    # ─────────────────────────────────────────────
    
    def test_07_circle_diagnostic(self):
        """GET /api/circle/diagnostic returns Circle API health check"""
        resp = self.session.get(f"{BASE_URL}/api/circle/diagnostic")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert 'service' in data
        assert 'api_status' in data
        assert 'segregated_wallets' in data
        assert 'onchain_balances' in data
        assert 'rules' in data
        
        # Check segregated wallets
        wallets = data['segregated_wallets']
        assert 'client' in wallets
        assert 'treasury' in wallets
        assert 'revenue' in wallets
        
        # Check on-chain balances
        onchain = data['onchain_balances']
        assert 'wallets' in onchain
        assert 'total_usdc' in onchain
        
        print(f"✓ Circle diagnostic:")
        print(f"  Service: {data['service']}")
        print(f"  API Status: {data['api_status']}")
        print(f"  Environment: {data.get('environment', 'N/A')}")
        print(f"  Total USDC: {onchain['total_usdc']}")
    
    # ─────────────────────────────────────────────
    # SEGREGATION
    # ─────────────────────────────────────────────
    
    def test_08_segregation_summary(self):
        """GET /api/circle/segregation/summary returns movement statistics"""
        resp = self.session.get(f"{BASE_URL}/api/circle/segregation/summary")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert 'total_movements' in data
        assert 'confirmed' in data
        assert 'pending' in data
        assert 'wallets' in data
        
        print(f"✓ Segregation summary:")
        print(f"  Total movements: {data['total_movements']}")
        print(f"  Confirmed: {data['confirmed']}")
        print(f"  Pending: {data['pending']}")
    
    def test_09_segregation_reconciliation(self):
        """GET /api/circle/segregation/reconciliation returns on-chain vs ledger comparison"""
        resp = self.session.get(f"{BASE_URL}/api/circle/segregation/reconciliation")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert 'status' in data
        assert 'onchain_balances' in data
        assert 'ledger_balances' in data
        assert 'discrepancies' in data
        assert 'reconciled_at' in data
        
        # Status should be 'clean' if no discrepancies
        print(f"✓ Reconciliation status: {data['status']}")
        print(f"  On-chain: {data['onchain_balances']}")
        print(f"  Ledger: {data['ledger_balances']}")
        print(f"  Discrepancies: {len(data['discrepancies'])}")
    
    def test_10_segregation_movements(self):
        """GET /api/circle/segregation/movements returns list of movements"""
        resp = self.session.get(f"{BASE_URL}/api/circle/segregation/movements")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert 'movements' in data
        assert 'count' in data
        assert isinstance(data['movements'], list)
        
        print(f"✓ Segregation movements: {data['count']} records")
    
    def test_11_segregation_move_requires_admin(self):
        """POST /api/circle/segregation/move requires admin role"""
        # This should work since we're logged in as admin
        resp = self.session.post(f"{BASE_URL}/api/circle/segregation/move", json={
            "from_role": "treasury",
            "to_role": "revenue",
            "amount_usdc": 0.01,
            "reason": "test_rebalance"
        })
        # Should succeed (200) or fail with business logic (not 403)
        assert resp.status_code in [200, 201], f"Admin move failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert 'movement_id' in data or 'from_wallet' in data
        print(f"✓ Admin segregation move recorded: {data}")
    
    # ─────────────────────────────────────────────
    # AUTO-OPERATION LOOP
    # ─────────────────────────────────────────────
    
    def test_12_auto_op_status(self):
        """GET /api/circle/auto-op/status returns loop status with fail_safes"""
        resp = self.session.get(f"{BASE_URL}/api/circle/auto-op/status")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert 'running' in data
        assert 'cycle_count' in data
        assert 'operations_executed' in data
        assert 'operations_blocked' in data
        assert 'fail_safes' in data
        
        # Check fail_safes structure
        fail_safes = data['fail_safes']
        assert 'real_mode_only' in fail_safes
        assert 'simulation_blocked' in fail_safes
        
        print(f"✓ Auto-op status:")
        print(f"  Running: {data['running']}")
        print(f"  Cycles: {data['cycle_count']}")
        print(f"  Executed: {data['operations_executed']}")
        print(f"  Blocked: {data['operations_blocked']}")
        print(f"  Fail-safes: {fail_safes}")
    
    def test_13_auto_op_start(self):
        """POST /api/circle/auto-op/start starts the loop (admin only)"""
        resp = self.session.post(f"{BASE_URL}/api/circle/auto-op/start")
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert data.get('status') == 'started'
        print(f"✓ Auto-op start: {data}")
    
    def test_14_auto_op_stop(self):
        """POST /api/circle/auto-op/stop stops the loop (admin only)"""
        resp = self.session.post(f"{BASE_URL}/api/circle/auto-op/stop")
        assert resp.status_code == 200, f"Failed: {resp.status_code} - {resp.text}"
        data = resp.json()
        assert data.get('status') == 'stopped'
        print(f"✓ Auto-op stop: {data}")
    
    def test_15_auto_op_restart(self):
        """Restart auto-op loop after stopping"""
        resp = self.session.post(f"{BASE_URL}/api/circle/auto-op/start")
        assert resp.status_code == 200
        print(f"✓ Auto-op restarted")
    
    # ─────────────────────────────────────────────
    # FAIL-SAFE REPORT
    # ─────────────────────────────────────────────
    
    def test_16_fail_safe_report(self):
        """GET /api/circle/fail-safe/report returns reality check with rules enforced"""
        resp = self.session.get(f"{BASE_URL}/api/circle/fail-safe/report")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert 'fail_safe_active' in data
        assert data['fail_safe_active'] == True
        assert 'rules' in data
        assert 'current_state' in data
        assert 'statistics' in data
        
        # Check rules
        rules = data['rules']
        assert rules.get('no_simulation') == True
        assert rules.get('no_artificial_funds') == True
        assert rules.get('no_uncovered_operations') == True
        assert rules.get('real_execution_only') == True
        
        # Check current state
        state = data['current_state']
        assert 'total_usdc_onchain' in state
        assert 'client_wallet' in state
        assert 'treasury_wallet' in state
        assert 'revenue_wallet' in state
        
        print(f"✓ Fail-safe report:")
        print(f"  Active: {data['fail_safe_active']}")
        print(f"  Rules: {rules}")
        print(f"  Total USDC: {state['total_usdc_onchain']}")
        print(f"  Statistics: {data['statistics']}")
    
    # ─────────────────────────────────────────────
    # EXISTING STRATEGIC ENDPOINT
    # ─────────────────────────────────────────────
    
    def test_17_real_treasury_still_works(self):
        """GET /api/strategic/real-treasury still returns on-chain verified balances"""
        resp = self.session.get(f"{BASE_URL}/api/strategic/real-treasury")
        assert resp.status_code == 200, f"Failed: {resp.text}"
        data = resp.json()
        
        assert 'type' in data
        assert data['type'] == 'REAL_TREASURY'
        assert 'assets' in data
        assert 'total_eur_value' in data
        
        print(f"✓ Real treasury endpoint still working:")
        print(f"  Type: {data['type']}")
        print(f"  Total EUR: {data['total_eur_value']}")
    
    # ─────────────────────────────────────────────
    # AUTH REQUIRED
    # ─────────────────────────────────────────────
    
    def test_18_endpoints_require_auth(self):
        """All Circle endpoints require Bearer token auth"""
        no_auth_session = requests.Session()
        no_auth_session.headers.update({'Content-Type': 'application/json'})
        
        endpoints = [
            ('GET', '/api/circle/wallets/balances'),
            ('GET', '/api/circle/wallets/client/balance'),
            ('GET', '/api/circle/diagnostic'),
            ('GET', '/api/circle/segregation/summary'),
            ('GET', '/api/circle/segregation/reconciliation'),
            ('GET', '/api/circle/segregation/movements'),
            ('GET', '/api/circle/auto-op/status'),
            ('GET', '/api/circle/fail-safe/report'),
        ]
        
        for method, endpoint in endpoints:
            if method == 'GET':
                resp = no_auth_session.get(f"{BASE_URL}{endpoint}")
            else:
                resp = no_auth_session.post(f"{BASE_URL}{endpoint}")
            
            assert resp.status_code in [401, 403], f"{endpoint} should require auth, got {resp.status_code}"
        
        print(f"✓ All {len(endpoints)} Circle endpoints require authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
