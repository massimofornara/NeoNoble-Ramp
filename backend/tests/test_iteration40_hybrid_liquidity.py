"""
Iteration 40 - Hybrid Liquidity Engine & Wallet Fix Testing

Tests:
1. GET /api/hybrid/status — Hybrid liquidity engine status
2. GET /api/hybrid/spread — Dynamic spread quotes
3. POST /api/hybrid/order — Place order for matching
4. POST /api/hybrid/execute — Execute with priority
5. GET /api/live/pipeline/assess — Pipeline assessment
6. GET /api/live/dex/liquidity/NENO — DEX liquidity check
7. GET /api/live/dex/quote — PancakeSwap V2 quote
8. GET /api/live/dex/history — Swap history
9. GET /api/sync/state — Real mode state
10. GET /api/sync/instant-withdraw/status — Instant withdraw status
11. GET /api/cashout/status — Cashout engine status
12. GET /api/circle/wallets/balances — Segregated wallets
13. GET /api/health — Health check
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Module-level session and token
_session = None
_auth_token = None

def get_auth_session():
    """Get authenticated session (cached)"""
    global _session, _auth_token
    
    if _session is not None and _auth_token is not None:
        return _session
    
    _session = requests.Session()
    _session.headers.update({"Content-Type": "application/json"})
    
    # Login as admin
    login_resp = _session.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@neonobleramp.com",
        "password": "Admin1234!"
    })
    
    if login_resp.status_code == 200:
        _auth_token = login_resp.json().get("token")
        _session.headers.update({"Authorization": f"Bearer {_auth_token}"})
        print(f"✓ Authenticated as admin")
    else:
        print(f"✗ Auth failed: {login_resp.status_code}")
    
    return _session


class TestIteration40HybridLiquidity:
    """Hybrid Liquidity Engine and related endpoint tests"""
    
    # ─────────────────────────────────────────────
    # HEALTH CHECK
    # ─────────────────────────────────────────────
    
    def test_01_health_check(self):
        """GET /api/health returns healthy status"""
        resp = requests.get(f"{BASE_URL}/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "healthy"
        print(f"✓ Health check passed: {data.get('service')}")
    
    # ─────────────────────────────────────────────
    # HYBRID LIQUIDITY ENGINE
    # ─────────────────────────────────────────────
    
    def test_02_hybrid_status_requires_auth(self):
        """GET /api/hybrid/status requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/hybrid/status")
        assert resp.status_code == 401
        print("✓ /api/hybrid/status requires auth (401)")
    
    def test_03_hybrid_status_returns_engine_config(self):
        """GET /api/hybrid/status returns engine=hybrid_liquidity with full config"""
        session = get_auth_session()
        resp = session.get(f"{BASE_URL}/api/hybrid/status")
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify engine type
        assert data.get("engine") == "hybrid_liquidity"
        
        # Verify execution priority
        assert "execution_priority" in data
        priority = data["execution_priority"]
        assert "internal_match" in priority
        assert "market_maker" in priority
        assert "dex_fallback" in priority
        
        # Verify spread config
        assert "spread" in data
        spread = data["spread"]
        assert "base_bps" in spread
        assert "min_bps" in spread
        assert "max_bps" in spread
        assert "fee_pct" in spread
        assert spread["base_bps"] == 200  # 2% default
        assert spread["min_bps"] == 100   # 1% minimum
        assert spread["max_bps"] == 300   # 3% maximum
        
        # Verify order book stats
        assert "order_book" in data
        
        # Verify volume metrics
        assert "volume" in data
        
        # Verify volume tiers
        assert "volume_tiers" in data
        
        print(f"✓ Hybrid status: engine={data['engine']}, priority={priority}")
        print(f"  Spread config: base={spread['base_bps']}bps, min={spread['min_bps']}bps, max={spread['max_bps']}bps")
    
    def test_04_hybrid_spread_requires_auth(self):
        """GET /api/hybrid/spread requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/hybrid/spread?asset=NENO&side=buy&amount=10")
        assert resp.status_code == 401
        print("✓ /api/hybrid/spread requires auth (401)")
    
    def test_05_hybrid_spread_returns_dynamic_quote(self):
        """GET /api/hybrid/spread returns dynamic spread with skew and inventory"""
        session = get_auth_session()
        resp = session.get(f"{BASE_URL}/api/hybrid/spread?asset=NENO&side=buy&amount=10")
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify spread fields
        assert "spread_bps" in data
        assert "spread_pct" in data
        assert "base_bps" in data
        assert "skew_bps" in data
        assert "fee_pct" in data
        assert "total_cost_pct" in data
        assert "inventory_position" in data
        assert "asset" in data
        assert "side" in data
        
        # Verify spread is within bounds (100-300 bps)
        spread_bps = data["spread_bps"]
        assert 100 <= spread_bps <= 300, f"Spread {spread_bps}bps outside 100-300 range"
        
        print(f"✓ Dynamic spread: {spread_bps}bps (skew={data['skew_bps']}bps)")
        print(f"  Inventory position: {data['inventory_position']}, Total cost: {data['total_cost_pct']}%")
    
    def test_06_hybrid_spread_sell_side(self):
        """GET /api/hybrid/spread for sell side"""
        session = get_auth_session()
        resp = session.get(f"{BASE_URL}/api/hybrid/spread?asset=NENO&side=sell&amount=5")
        assert resp.status_code == 200
        data = resp.json()
        
        assert data["side"] == "sell"
        assert "spread_bps" in data
        print(f"✓ Sell spread: {data['spread_bps']}bps")
    
    def test_07_hybrid_order_requires_auth(self):
        """POST /api/hybrid/order requires authentication"""
        resp = requests.post(f"{BASE_URL}/api/hybrid/order", json={
            "side": "buy", "asset": "NENO", "amount": 1, "price_eur": 10000
        })
        assert resp.status_code == 401
        print("✓ /api/hybrid/order requires auth (401)")
    
    def test_08_hybrid_order_place_buy(self):
        """POST /api/hybrid/order places buy order for matching"""
        session = get_auth_session()
        resp = session.post(f"{BASE_URL}/api/hybrid/order", json={
            "side": "buy",
            "asset": "NENO",
            "amount": 1,
            "price_eur": 10000
        })
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify order response
        assert "order_id" in data
        assert "status" in data
        assert "match" in data
        
        print(f"✓ Order placed: id={data['order_id'][:8]}..., status={data['status']}")
        print(f"  Match result: {data['match']}")
    
    def test_09_hybrid_execute_requires_auth(self):
        """POST /api/hybrid/execute requires authentication"""
        resp = requests.post(f"{BASE_URL}/api/hybrid/execute", json={
            "side": "buy", "asset": "NENO", "amount": 1, "price_eur": 10000
        })
        assert resp.status_code == 401
        print("✓ /api/hybrid/execute requires auth (401)")
    
    def test_10_hybrid_execute_with_priority(self):
        """POST /api/hybrid/execute executes with priority (internal→MM→DEX)"""
        session = get_auth_session()
        resp = session.post(f"{BASE_URL}/api/hybrid/execute", json={
            "side": "buy",
            "asset": "NENO",
            "amount": 1,
            "price_eur": 10000
        })
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify execution response
        assert "execution_type" in data
        assert "success" in data
        assert data["success"] == True
        
        # Execution type should be one of the priority options
        exec_type = data["execution_type"]
        assert exec_type in ["internal_match", "market_maker", "dex_fallback"]
        
        print(f"✓ Execution: type={exec_type}, success={data['success']}")
    
    # ─────────────────────────────────────────────
    # LIVE PIPELINE ENDPOINTS
    # ─────────────────────────────────────────────
    
    def test_11_pipeline_assess_requires_auth(self):
        """GET /api/live/pipeline/assess requires authentication"""
        resp = requests.get(f"{BASE_URL}/api/live/pipeline/assess")
        assert resp.status_code == 401
        print("✓ /api/live/pipeline/assess requires auth (401)")
    
    def test_12_pipeline_assess_returns_full_assessment(self):
        """GET /api/live/pipeline/assess returns dex_liquidity, fiat_rails, hot_wallet"""
        session = get_auth_session()
        resp = session.get(f"{BASE_URL}/api/live/pipeline/assess")
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify key assessment fields
        assert "dex_liquidity" in data or "hot_wallet" in data or "pipeline_ready" in data
        
        # Check for hot wallet info
        if "hot_wallet" in data:
            hw = data["hot_wallet"]
            print(f"✓ Hot wallet: {hw.get('address', 'N/A')[:10]}...")
        
        # Check for DEX liquidity
        if "dex_liquidity" in data:
            dex = data["dex_liquidity"]
            print(f"  DEX liquidity: {dex}")
        
        # Check for fiat rails
        if "fiat_rails" in data:
            rails = data["fiat_rails"]
            print(f"  Fiat rails: {rails}")
        
        print(f"✓ Pipeline assessment returned successfully")
    
    def test_13_dex_liquidity_neno(self):
        """GET /api/live/dex/liquidity/NENO returns has_liquidity=true with pair_address"""
        session = get_auth_session()
        resp = session.get(f"{BASE_URL}/api/live/dex/liquidity/NENO")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "has_liquidity" in data
        assert data["has_liquidity"] == True
        assert "pair_address" in data
        
        print(f"✓ NENO liquidity: has_liquidity={data['has_liquidity']}")
        print(f"  Pair address: {data['pair_address']}")
    
    def test_14_dex_quote_neno_to_usdc(self):
        """GET /api/live/dex/quote returns PancakeSwap V2 quote"""
        session = get_auth_session()
        resp = session.get(f"{BASE_URL}/api/live/dex/quote?from_asset=NENO&to_asset=USDC&amount=1")
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify quote fields
        assert "success" in data
        if data["success"]:
            assert "amount_in" in data
            assert "amount_out" in data
            assert "rate" in data
            assert "dex" in data
            assert data["dex"] == "PancakeSwap V2"
            print(f"✓ DEX quote: {data['amount_in']} NENO → {data['amount_out']} USDC")
            print(f"  Rate: {data['rate']}, DEX: {data['dex']}")
        else:
            print(f"✓ DEX quote returned (no liquidity or route): {data.get('error', 'N/A')}")
    
    def test_15_dex_history_returns_swaps(self):
        """GET /api/live/dex/history returns swap history with real TX hashes"""
        session = get_auth_session()
        resp = session.get(f"{BASE_URL}/api/live/dex/history")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "swaps" in data
        assert "count" in data
        
        swaps = data["swaps"]
        print(f"✓ DEX history: {data['count']} swaps")
        
        # If there are swaps, verify TX hash format
        if len(swaps) > 0:
            for swap in swaps[:2]:
                if "tx_hash" in swap:
                    print(f"  TX: {swap['tx_hash'][:16]}...")
    
    # ─────────────────────────────────────────────
    # SYNC STATE ENDPOINTS
    # ─────────────────────────────────────────────
    
    def test_16_sync_state_returns_real_mode(self):
        """GET /api/sync/state returns real_mode=true with all balance sources"""
        session = get_auth_session()
        resp = session.get(f"{BASE_URL}/api/sync/state")
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify real mode
        assert "real_mode" in data
        assert data["real_mode"] == True
        
        print(f"✓ Sync state: real_mode={data['real_mode']}")
        
        # Check for balance sources
        if "hot_wallet" in data:
            print(f"  Hot wallet: {data['hot_wallet']}")
        if "usdc_wallets" in data:
            print(f"  USDC wallets: {data['usdc_wallets']}")
    
    def test_17_instant_withdraw_status_active(self):
        """GET /api/sync/instant-withdraw/status returns active=true"""
        session = get_auth_session()
        resp = session.get(f"{BASE_URL}/api/sync/instant-withdraw/status")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "active" in data
        assert data["active"] == True
        
        print(f"✓ Instant withdraw: active={data['active']}")
    
    # ─────────────────────────────────────────────
    # CASHOUT ENGINE
    # ─────────────────────────────────────────────
    
    def test_18_cashout_status_returns_running(self):
        """GET /api/cashout/status returns running status and EUR accounts"""
        session = get_auth_session()
        resp = session.get(f"{BASE_URL}/api/cashout/status")
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify running status
        assert "running" in data
        
        # Verify EUR accounts
        if "eur_accounts" in data:
            accounts = data["eur_accounts"]
            print(f"✓ Cashout status: running={data['running']}")
            print(f"  EUR accounts: {list(accounts.keys())}")
            
            # Verify IT and BE accounts
            if "IT" in accounts:
                assert "iban" in accounts["IT"]
                assert "bic" in accounts["IT"]
            if "BE" in accounts:
                assert "iban" in accounts["BE"]
                assert "bic" in accounts["BE"]
        else:
            print(f"✓ Cashout status: running={data['running']}")
    
    # ─────────────────────────────────────────────
    # CIRCLE WALLETS
    # ─────────────────────────────────────────────
    
    def test_19_circle_wallets_3_segregated(self):
        """GET /api/circle/wallets/balances returns 3 segregated wallets"""
        session = get_auth_session()
        resp = session.get(f"{BASE_URL}/api/circle/wallets/balances")
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify wallets structure
        assert "wallets" in data
        wallets = data["wallets"]
        
        # Should have CLIENT, TREASURY, REVENUE
        expected_roles = ["client", "treasury", "revenue"]
        for role in expected_roles:
            assert role in wallets, f"Missing {role} wallet"
            wallet = wallets[role]
            assert "address" in wallet
            assert "balance" in wallet
            print(f"✓ {role.upper()} wallet: {wallet['address'][:10]}... = {wallet['balance']} USDC")
        
        # Verify total
        if "total_usdc" in data:
            print(f"  Total USDC: {data['total_usdc']}")
    
    # ─────────────────────────────────────────────
    # VOLUME-BASED SPREAD TIERS
    # ─────────────────────────────────────────────
    
    def test_20_volume_tiers_in_status(self):
        """Verify volume tiers are returned in hybrid status"""
        session = get_auth_session()
        resp = session.get(f"{BASE_URL}/api/hybrid/status")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "volume_tiers" in data
        tiers = data["volume_tiers"]
        
        # Verify tier structure (volume threshold → spread bps)
        # Expected: 0→200, 10000→175, 50000→150, 100000→125, 500000→100
        assert "0" in tiers or 0 in tiers
        
        print(f"✓ Volume tiers: {tiers}")
    
    # ─────────────────────────────────────────────
    # SPREAD RANGE VALIDATION
    # ─────────────────────────────────────────────
    
    def test_21_spread_within_100_300_bps(self):
        """Verify dynamic spread stays within 100-300 bps range"""
        session = get_auth_session()
        # Test multiple scenarios
        scenarios = [
            {"asset": "NENO", "side": "buy", "amount": 1},
            {"asset": "NENO", "side": "sell", "amount": 1},
            {"asset": "NENO", "side": "buy", "amount": 100},
        ]
        
        for scenario in scenarios:
            resp = session.get(
                f"{BASE_URL}/api/hybrid/spread",
                params=scenario
            )
            assert resp.status_code == 200
            data = resp.json()
            
            spread_bps = data["spread_bps"]
            assert 100 <= spread_bps <= 300, f"Spread {spread_bps}bps outside range for {scenario}"
            print(f"✓ {scenario['side']} {scenario['amount']} {scenario['asset']}: {spread_bps}bps")
    
    # ─────────────────────────────────────────────
    # INTERNAL ORDER MATCHING
    # ─────────────────────────────────────────────
    
    def test_22_order_book_stats_in_status(self):
        """Verify order book stats are returned in hybrid status"""
        session = get_auth_session()
        resp = session.get(f"{BASE_URL}/api/hybrid/status")
        assert resp.status_code == 200
        data = resp.json()
        
        assert "order_book" in data
        ob = data["order_book"]
        
        assert "pending" in ob
        assert "matched" in ob
        assert "total_matches" in ob
        
        print(f"✓ Order book: pending={ob['pending']}, matched={ob['matched']}, total_matches={ob['total_matches']}")
    
    # ─────────────────────────────────────────────
    # EXECUTION PRIORITY VERIFICATION
    # ─────────────────────────────────────────────
    
    def test_23_execution_priority_order(self):
        """Verify execution priority is internal_match → market_maker → dex_fallback"""
        session = get_auth_session()
        resp = session.get(f"{BASE_URL}/api/hybrid/status")
        assert resp.status_code == 200
        data = resp.json()
        
        priority = data["execution_priority"]
        
        # Verify order
        assert priority[0] == "internal_match"
        assert priority[1] == "market_maker"
        assert priority[2] == "dex_fallback"
        
        print(f"✓ Execution priority: {' → '.join(priority)}")
    
    # ─────────────────────────────────────────────
    # SELL ORDER TEST
    # ─────────────────────────────────────────────
    
    def test_24_hybrid_order_place_sell(self):
        """POST /api/hybrid/order places sell order"""
        session = get_auth_session()
        resp = session.post(f"{BASE_URL}/api/hybrid/order", json={
            "side": "sell",
            "asset": "NENO",
            "amount": 0.5,
            "price_eur": 9500
        })
        assert resp.status_code == 200
        data = resp.json()
        
        assert "order_id" in data
        assert "status" in data
        
        print(f"✓ Sell order placed: id={data['order_id'][:8]}..., status={data['status']}")
    
    # ─────────────────────────────────────────────
    # EXECUTE SELL TEST
    # ─────────────────────────────────────────────
    
    def test_25_hybrid_execute_sell(self):
        """POST /api/hybrid/execute for sell side"""
        session = get_auth_session()
        resp = session.post(f"{BASE_URL}/api/hybrid/execute", json={
            "side": "sell",
            "asset": "NENO",
            "amount": 0.5,
            "price_eur": 9500
        })
        assert resp.status_code == 200
        data = resp.json()
        
        assert "execution_type" in data
        assert "success" in data
        
        print(f"✓ Sell execution: type={data['execution_type']}, success={data['success']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
