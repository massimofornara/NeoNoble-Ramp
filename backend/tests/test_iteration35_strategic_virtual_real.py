"""
Iteration 35 - Strategic APIs: Virtual→Real Conversion, Payout Guard, IPO Roadmap

Tests:
1. GET /api/strategic/real-treasury — on-chain verified balances
2. GET /api/strategic/virtual-metrics — virtual demand with warning
3. GET /api/strategic/reconciliation — real vs virtual comparison
4. GET /api/strategic/payout-guard/NENO?amount=0.01 — should allow (NENO available)
5. GET /api/strategic/payout-guard/ETH?amount=1 — should BLOCK (0 WETH in hot wallet)
6. GET /api/strategic/payout-guard/EUR?amount=100 — should allow (Stripe handles)
7. GET /api/strategic/ipo-roadmap — returns 5 phases with capital and partners
8. POST /api/neno-exchange/withdraw-real with ETH asset — should be blocked by payout guard
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestStrategicAPIs:
    """Strategic Operations API tests - Virtual→Real conversion architecture"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for all tests"""
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@neonobleramp.com",
            "password": "Admin1234!"
        })
        if login_resp.status_code == 200:
            token = login_resp.json().get('token')
            self.session.headers.update({'Authorization': f'Bearer {token}'})
        else:
            pytest.skip("Authentication failed - skipping tests")
    
    # ─────────────────────────────────────────────
    # TEST 1: Real Treasury (On-Chain Verified)
    # ─────────────────────────────────────────────
    def test_01_real_treasury_returns_onchain_balances(self):
        """GET /api/strategic/real-treasury returns on-chain verified balances"""
        resp = self.session.get(f"{BASE_URL}/api/strategic/real-treasury")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        
        # Verify type is REAL_TREASURY
        assert data.get('type') == 'REAL_TREASURY', f"Expected type=REAL_TREASURY, got {data.get('type')}"
        
        # Verify assets structure
        assert 'assets' in data, "Missing 'assets' field"
        assets = data['assets']
        
        # Should have NENO with verified balance
        assert 'NENO' in assets, "Missing NENO in assets"
        neno = assets['NENO']
        assert 'balance' in neno, "NENO missing balance"
        assert neno.get('source') == 'on_chain_rpc', f"NENO source should be on_chain_rpc, got {neno.get('source')}"
        assert neno.get('verified') == True, "NENO should be verified"
        
        # Verify hot wallet address
        assert 'hot_wallet' in data, "Missing hot_wallet"
        assert data['hot_wallet'].startswith('0x'), "Hot wallet should be Ethereum address"
        
        # Verify block number (proves RPC call)
        assert 'block_number' in data, "Missing block_number"
        assert isinstance(data['block_number'], int), "block_number should be integer"
        
        # Verify total EUR value
        assert 'total_eur_value' in data, "Missing total_eur_value"
        
        # Verify real revenue tracking
        assert 'real_revenue' in data, "Missing real_revenue"
        assert 'total_fees_earned' in data['real_revenue'], "Missing total_fees_earned"
        assert 'real_trade_count' in data['real_revenue'], "Missing real_trade_count"
        
        print(f"✓ Real Treasury: EUR {data['total_eur_value']}, NENO: {neno['balance']}, Block: {data['block_number']}")
    
    # ─────────────────────────────────────────────
    # TEST 2: Virtual Metrics (NOT real money)
    # ─────────────────────────────────────────────
    def test_02_virtual_metrics_returns_warning(self):
        """GET /api/strategic/virtual-metrics returns virtual demand with warning"""
        resp = self.session.get(f"{BASE_URL}/api/strategic/virtual-metrics")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        
        # Verify type is VIRTUAL_METRICS
        assert data.get('type') == 'VIRTUAL_METRICS', f"Expected type=VIRTUAL_METRICS, got {data.get('type')}"
        
        # CRITICAL: Must have warning that these are NOT real money
        assert 'warning' in data, "Missing warning field"
        warning = data['warning'].lower()
        assert 'non' in warning or 'not' in warning, f"Warning should indicate NOT real money: {data['warning']}"
        
        # Verify volume breakdown
        assert 'total_ledger_volume_eur' in data, "Missing total_ledger_volume_eur"
        assert 'real_executed_volume_eur' in data, "Missing real_executed_volume_eur"
        assert 'virtual_demand_volume_eur' in data, "Missing virtual_demand_volume_eur"
        
        # Verify transaction counts
        assert 'total_transactions' in data, "Missing total_transactions"
        assert 'real_transactions' in data, "Missing real_transactions"
        assert 'virtual_transactions' in data, "Missing virtual_transactions"
        
        # Verify conversion rate
        assert 'conversion_rate_pct' in data, "Missing conversion_rate_pct"
        
        print(f"✓ Virtual Metrics: Total EUR {data['total_ledger_volume_eur']}, Real EUR {data['real_executed_volume_eur']}, Virtual EUR {data['virtual_demand_volume_eur']}, Conversion: {data['conversion_rate_pct']}%")
    
    # ─────────────────────────────────────────────
    # TEST 3: Reconciliation (Real vs Virtual)
    # ─────────────────────────────────────────────
    def test_03_reconciliation_compares_real_vs_virtual(self):
        """GET /api/strategic/reconciliation returns real vs virtual comparison"""
        resp = self.session.get(f"{BASE_URL}/api/strategic/reconciliation")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        
        # Verify reconciliation structure
        assert 'reconciliation' in data, "Missing reconciliation field"
        recon = data['reconciliation']
        
        assert 'real_treasury_eur' in recon, "Missing real_treasury_eur"
        assert 'virtual_demand_eur' in recon, "Missing virtual_demand_eur"
        assert 'real_volume_eur' in recon, "Missing real_volume_eur"
        assert 'real_fee_revenue_eur' in recon, "Missing real_fee_revenue_eur"
        
        # Verify conversion pipeline explanation
        assert 'conversion_pipeline' in recon, "Missing conversion_pipeline"
        pipeline = recon['conversion_pipeline']
        assert 'virtual_demand' in pipeline, "Missing virtual_demand in pipeline"
        assert 'real_converted' in pipeline, "Missing real_converted in pipeline"
        assert 'conversion_rate' in pipeline, "Missing conversion_rate in pipeline"
        
        # Verify principle statement
        assert 'principle' in recon, "Missing principle statement"
        
        # Verify nested real_treasury and virtual_metrics
        assert 'real_treasury' in data, "Missing real_treasury in reconciliation response"
        assert 'virtual_metrics' in data, "Missing virtual_metrics in reconciliation response"
        
        print(f"✓ Reconciliation: Real Treasury EUR {recon['real_treasury_eur']}, Virtual Demand EUR {recon['virtual_demand_eur']}, Conversion: {pipeline['conversion_rate']}")
    
    # ─────────────────────────────────────────────
    # TEST 4: Payout Guard - NENO (should ALLOW)
    # ─────────────────────────────────────────────
    def test_04_payout_guard_neno_allows_small_amount(self):
        """GET /api/strategic/payout-guard/NENO?amount=0.01 should allow (NENO available)"""
        resp = self.session.get(f"{BASE_URL}/api/strategic/payout-guard/NENO?amount=0.01")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        
        # Verify asset
        assert data.get('asset') == 'NENO', f"Expected asset=NENO, got {data.get('asset')}"
        
        # Verify requested amount
        assert data.get('requested') == 0.01, f"Expected requested=0.01, got {data.get('requested')}"
        
        # Should allow payout (NENO balance ~396.99)
        assert data.get('can_payout') == True, f"Expected can_payout=True for 0.01 NENO, got {data.get('can_payout')}"
        assert data.get('blocked') == False or data.get('blocked') is None, f"Should not be blocked for 0.01 NENO"
        
        # Verify available balance
        assert 'available' in data, "Missing available balance"
        assert data['available'] > 0.01, f"Available NENO should be > 0.01, got {data['available']}"
        
        # Verify source is on-chain
        assert data.get('source') == 'on_chain_rpc', f"Source should be on_chain_rpc, got {data.get('source')}"
        assert data.get('verified') == True, "Should be verified"
        
        print(f"✓ Payout Guard NENO: can_payout=True, available={data['available']}, requested=0.01")
    
    # ─────────────────────────────────────────────
    # TEST 5: Payout Guard - ETH (should BLOCK)
    # ─────────────────────────────────────────────
    def test_05_payout_guard_eth_blocks_insufficient_funds(self):
        """GET /api/strategic/payout-guard/ETH?amount=1 should BLOCK (0 WETH in hot wallet)"""
        resp = self.session.get(f"{BASE_URL}/api/strategic/payout-guard/ETH?amount=1")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        
        # Verify asset (should be uppercase)
        assert data.get('asset') == 'ETH', f"Expected asset=ETH, got {data.get('asset')}"
        
        # Verify requested amount
        assert data.get('requested') == 1, f"Expected requested=1, got {data.get('requested')}"
        
        # Should BLOCK payout (0 WETH in hot wallet)
        assert data.get('can_payout') == False, f"Expected can_payout=False for 1 ETH (0 WETH available), got {data.get('can_payout')}"
        assert data.get('blocked') == True, f"Expected blocked=True for 1 ETH"
        
        # Verify reason is provided
        assert 'reason' in data, "Missing reason for block"
        assert data['reason'] is not None, "Reason should not be None when blocked"
        
        print(f"✓ Payout Guard ETH: can_payout=False, blocked=True, reason={data.get('reason')}")
    
    # ─────────────────────────────────────────────
    # TEST 6: Payout Guard - EUR (Stripe handles)
    # ─────────────────────────────────────────────
    def test_06_payout_guard_eur_allows_stripe(self):
        """GET /api/strategic/payout-guard/EUR?amount=100 should allow (Stripe handles)"""
        resp = self.session.get(f"{BASE_URL}/api/strategic/payout-guard/EUR?amount=100")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        
        # Verify asset
        assert data.get('asset') == 'EUR', f"Expected asset=EUR, got {data.get('asset')}"
        
        # Verify requested amount
        assert data.get('requested') == 100, f"Expected requested=100, got {data.get('requested')}"
        
        # Should allow payout (Stripe handles balance check at execution)
        assert data.get('can_payout') == True, f"Expected can_payout=True for EUR (Stripe handles), got {data.get('can_payout')}"
        
        # Verify method is stripe_sepa
        assert data.get('method') == 'stripe_sepa', f"Expected method=stripe_sepa, got {data.get('method')}"
        
        # Verify note about Stripe
        assert 'note' in data, "Missing note about Stripe"
        
        print(f"✓ Payout Guard EUR: can_payout=True, method=stripe_sepa")
    
    # ─────────────────────────────────────────────
    # TEST 7: IPO Roadmap (5 phases)
    # ─────────────────────────────────────────────
    def test_07_ipo_roadmap_returns_5_phases(self):
        """GET /api/strategic/ipo-roadmap returns 5 phases with capital and partners"""
        resp = self.session.get(f"{BASE_URL}/api/strategic/ipo-roadmap")
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        
        data = resp.json()
        
        # Verify title
        assert 'title' in data, "Missing title"
        
        # Verify 5 phases
        assert 'phases' in data, "Missing phases"
        phases = data['phases']
        assert len(phases) == 5, f"Expected 5 phases, got {len(phases)}"
        
        # Verify each phase has required fields
        for i, phase in enumerate(phases):
            assert 'id' in phase, f"Phase {i+1} missing id"
            assert 'name' in phase, f"Phase {i+1} missing name"
            assert 'objectives' in phase, f"Phase {i+1} missing objectives"
            assert 'deliverables' in phase, f"Phase {i+1} missing deliverables"
            assert 'capital_min_eur' in phase, f"Phase {i+1} missing capital_min_eur"
            assert 'capital_recommended_eur' in phase, f"Phase {i+1} missing capital_recommended_eur"
            assert 'kpis' in phase, f"Phase {i+1} missing kpis"
            assert 'risks' in phase, f"Phase {i+1} missing risks"
        
        # Verify capital summary
        assert 'capital_summary' in data, "Missing capital_summary"
        cap = data['capital_summary']
        assert 'total_min' in cap, "Missing total_min in capital_summary"
        assert 'total_recommended' in cap, "Missing total_recommended in capital_summary"
        
        # Verify partner matrix
        assert 'partner_matrix' in data, "Missing partner_matrix"
        partners = data['partner_matrix']
        assert len(partners) > 0, "Partner matrix should not be empty"
        
        # Verify conversion model
        assert 'conversion_model' in data, "Missing conversion_model"
        conv = data['conversion_model']
        assert 'principle' in conv, "Missing principle in conversion_model"
        assert 'rules' in conv, "Missing rules in conversion_model"
        assert 'api_endpoints' in conv, "Missing api_endpoints in conversion_model"
        
        print(f"✓ IPO Roadmap: {len(phases)} phases, Capital Min EUR {cap['total_min']:,}, Recommended EUR {cap['total_recommended']:,}")
    
    # ─────────────────────────────────────────────
    # TEST 8: Auth Required for Strategic APIs
    # ─────────────────────────────────────────────
    def test_08_strategic_apis_require_auth(self):
        """Strategic APIs should return 401 without auth"""
        no_auth_session = requests.Session()
        no_auth_session.headers.update({'Content-Type': 'application/json'})
        
        endpoints = [
            '/api/strategic/real-treasury',
            '/api/strategic/virtual-metrics',
            '/api/strategic/reconciliation',
            '/api/strategic/payout-guard/NENO?amount=1',
            '/api/strategic/ipo-roadmap',
        ]
        
        for endpoint in endpoints:
            resp = no_auth_session.get(f"{BASE_URL}{endpoint}")
            assert resp.status_code == 401, f"Expected 401 for {endpoint} without auth, got {resp.status_code}"
        
        print(f"✓ All {len(endpoints)} strategic endpoints require auth (401 without token)")


class TestPayoutGuardIntegration:
    """Test payout guard integration with withdraw-real endpoint"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get auth token for all tests"""
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        
        # Login as admin
        login_resp = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@neonobleramp.com",
            "password": "Admin1234!"
        })
        if login_resp.status_code == 200:
            token = login_resp.json().get('token')
            self.session.headers.update({'Authorization': f'Bearer {token}'})
        else:
            pytest.skip("Authentication failed - skipping tests")
    
    def test_09_withdraw_real_eth_blocked_by_payout_guard(self):
        """POST /api/neno-exchange/withdraw-real with ETH should be blocked by payout guard"""
        # First verify payout guard blocks ETH
        guard_resp = self.session.get(f"{BASE_URL}/api/strategic/payout-guard/ETH?amount=0.1")
        assert guard_resp.status_code == 200
        guard_data = guard_resp.json()
        
        # ETH should be blocked (0 WETH in hot wallet)
        if guard_data.get('can_payout') == False:
            # Now try to withdraw - should be blocked
            withdraw_resp = self.session.post(f"{BASE_URL}/api/neno-exchange/withdraw-real", json={
                "asset": "ETH",
                "amount": 0.1,
                "destination_address": "0xf44C81dbab89941173d0d49C1CEA876950eDCfd3"
            })
            
            # Should either return error or blocked status
            # Accept 400, 403, or 200 with blocked=True
            if withdraw_resp.status_code == 200:
                data = withdraw_resp.json()
                # If 200, should indicate blocked
                assert data.get('blocked') == True or data.get('status') == 'blocked' or 'insufficient' in str(data).lower(), \
                    f"Expected blocked response for ETH withdrawal, got {data}"
            else:
                # 400 or 403 is acceptable for blocked withdrawal
                assert withdraw_resp.status_code in [400, 403, 422], \
                    f"Expected 400/403/422 for blocked ETH withdrawal, got {withdraw_resp.status_code}: {withdraw_resp.text}"
            
            print(f"✓ ETH withdrawal blocked by payout guard (status: {withdraw_resp.status_code})")
        else:
            # If ETH is somehow available, skip this test
            pytest.skip("ETH is available in hot wallet - cannot test block scenario")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
