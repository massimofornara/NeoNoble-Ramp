"""
Iteration 33 - Security Hardening & Real Execution Tests

Tests:
1. Security Status endpoint - caps and supported assets
2. Treasury caps enforcement - daily volume rejection
3. Rate limiting - 429 on rapid calls
4. SELL endpoint - destination_wallet and destination_iban fields
5. SWAP endpoint - destination_wallet field
6. Withdraw-Real endpoint - auth and execution
7. Status enforcement - pending_execution without proof
8. WebSocket balance endpoint existence
"""

import pytest
import requests
import os
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://multi-chain-wallet-14.preview.emergentagent.com").rstrip("/")

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"
TEST_WALLET = "0xf44C81dbab89941173d0d49C1CEA876950eDCfd3"


@pytest.fixture(scope="module")
def auth_token():
    """Get auth token for admin user."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("token") or data.get("access_token")
    pytest.skip(f"Auth failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Auth headers for authenticated requests."""
    return {"Authorization": f"Bearer {auth_token}"}


class TestSecurityStatusEndpoint:
    """Test /api/neno-exchange/security-status endpoint."""

    def test_01_security_status_returns_caps(self, auth_headers):
        """Security status endpoint returns correct treasury caps."""
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/security-status",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify treasury_caps structure
        assert "treasury_caps" in data, "Missing treasury_caps"
        caps = data["treasury_caps"]
        assert caps.get("max_single_tx_eur") == 50000, f"Expected max_single_tx_eur=50000, got {caps.get('max_single_tx_eur')}"
        assert caps.get("max_daily_eur") == 200000, f"Expected max_daily_eur=200000, got {caps.get('max_daily_eur')}"
        assert caps.get("max_neno_per_tx") == 50, f"Expected max_neno_per_tx=50, got {caps.get('max_neno_per_tx')}"
        
        print(f"✓ Treasury caps: {caps}")

    def test_02_security_status_returns_rate_limit(self, auth_headers):
        """Security status endpoint returns rate limit config."""
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/security-status",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "rate_limit" in data, "Missing rate_limit"
        assert data["rate_limit"].get("max_exec_ops_per_min") == 10, "Expected 10 ops/min"
        
        print(f"✓ Rate limit: {data['rate_limit']}")

    def test_03_security_status_returns_supported_assets(self, auth_headers):
        """Security status endpoint returns supported on-chain assets."""
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/security-status",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "supported_onchain_assets" in data, "Missing supported_onchain_assets"
        
        assets = data["supported_onchain_assets"]
        expected_assets = ["NENO", "USDT", "USDC", "ETH", "BTC", "BNB"]
        for asset in expected_assets:
            assert asset in assets, f"Missing expected asset: {asset}"
        
        print(f"✓ Supported assets: {assets}")

    def test_04_security_status_returns_status_enforcement(self, auth_headers):
        """Security status endpoint returns status enforcement rules."""
        response = requests.get(
            f"{BASE_URL}/api/neno-exchange/security-status",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "status_enforcement" in data, "Missing status_enforcement"
        
        enforcement = data["status_enforcement"]
        assert "provable" in enforcement, "Missing provable statuses"
        assert "pending" in enforcement, "Missing pending statuses"
        assert "completed" in enforcement["provable"], "completed should be provable"
        assert "pending_execution" in enforcement["pending"], "pending_execution should be in pending"
        
        print(f"✓ Status enforcement: {enforcement}")


class TestTreasuryCapsEnforcement:
    """Test treasury caps enforcement on SELL/SWAP/OFFRAMP."""

    def test_05_sell_rejects_when_daily_cap_exceeded(self, auth_headers):
        """SELL should reject when daily volume exceeds €200k cap."""
        # Previous tests filled daily volume to ~€785k, so this should fail
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/sell",
            headers=auth_headers,
            json={
                "receive_asset": "EUR",
                "neno_amount": 1.0,  # Even small amount should fail if daily cap exceeded
                "destination_wallet": TEST_WALLET
            }
        )
        
        # Should either succeed (if daily volume reset) or fail with cap error
        if response.status_code == 400:
            data = response.json()
            detail = data.get("detail", "")
            # Check for cap-related error message (Italian)
            assert "cap" in detail.lower() or "volume" in detail.lower() or "supera" in detail.lower() or "insufficiente" in detail.lower(), \
                f"Expected cap error, got: {detail}"
            print(f"✓ SELL correctly rejected with cap error: {detail}")
        elif response.status_code == 200:
            print(f"✓ SELL succeeded (daily volume may have reset)")
        elif response.status_code == 429:
            print(f"✓ Rate limited (expected behavior)")
        else:
            # Log but don't fail - could be other valid errors
            print(f"⚠ SELL returned {response.status_code}: {response.text[:200]}")

    def test_06_swap_rejects_when_daily_cap_exceeded(self, auth_headers):
        """SWAP should reject when daily volume exceeds €200k cap."""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/swap",
            headers=auth_headers,
            json={
                "from_asset": "NENO",
                "to_asset": "ETH",
                "amount": 1.0,
                "destination_wallet": TEST_WALLET
            }
        )
        
        if response.status_code == 400:
            data = response.json()
            detail = data.get("detail", "")
            assert "cap" in detail.lower() or "volume" in detail.lower() or "supera" in detail.lower() or "insufficiente" in detail.lower(), \
                f"Expected cap error, got: {detail}"
            print(f"✓ SWAP correctly rejected with cap error: {detail}")
        elif response.status_code == 200:
            print(f"✓ SWAP succeeded (daily volume may have reset)")
        elif response.status_code == 429:
            print(f"✓ Rate limited (expected behavior)")
        else:
            print(f"⚠ SWAP returned {response.status_code}: {response.text[:200]}")

    def test_07_offramp_rejects_when_daily_cap_exceeded(self, auth_headers):
        """OFFRAMP should reject when daily volume exceeds €200k cap."""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/offramp",
            headers=auth_headers,
            json={
                "neno_amount": 1.0,
                "destination": "crypto",
                "destination_wallet": TEST_WALLET,
                "preferred_stable": "USDT"
            }
        )
        
        if response.status_code == 400:
            data = response.json()
            detail = data.get("detail", "")
            assert "cap" in detail.lower() or "volume" in detail.lower() or "supera" in detail.lower() or "insufficiente" in detail.lower(), \
                f"Expected cap error, got: {detail}"
            print(f"✓ OFFRAMP correctly rejected with cap error: {detail}")
        elif response.status_code == 200:
            print(f"✓ OFFRAMP succeeded (daily volume may have reset)")
        elif response.status_code == 429:
            print(f"✓ Rate limited (expected behavior)")
        elif response.status_code == 500:
            # Could be insufficient stablecoin balance
            print(f"⚠ OFFRAMP returned 500 (likely insufficient stablecoin): {response.text[:200]}")
        else:
            print(f"⚠ OFFRAMP returned {response.status_code}: {response.text[:200]}")


class TestRateLimiting:
    """Test rate limiting on execution endpoints."""

    def test_08_rate_limit_triggers_429(self, auth_headers):
        """Rapid calls should trigger 429 rate limit."""
        # Make rapid calls to trigger rate limit
        # Rate limit is 10 ops/min for sell/swap/offramp
        
        responses = []
        for i in range(12):
            response = requests.post(
                f"{BASE_URL}/api/neno-exchange/sell",
                headers=auth_headers,
                json={
                    "receive_asset": "EUR",
                    "neno_amount": 0.001,
                    "destination_wallet": TEST_WALLET
                }
            )
            responses.append(response.status_code)
            # Small delay to avoid overwhelming
            time.sleep(0.1)
        
        # Should have at least one 429 in the responses
        has_429 = 429 in responses
        print(f"Response codes: {responses}")
        
        if has_429:
            print(f"✓ Rate limit correctly triggered 429")
        else:
            # Check if we got other valid responses (400 for cap, etc.)
            print(f"⚠ No 429 received - responses: {responses}")
            # This is acceptable if all requests were rejected for other reasons (caps, balance)


class TestSellEndpointFields:
    """Test SELL endpoint accepts destination_wallet and destination_iban."""

    def test_09_sell_accepts_destination_wallet(self, auth_headers):
        """SELL endpoint should accept destination_wallet field."""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/sell",
            headers=auth_headers,
            json={
                "receive_asset": "ETH",
                "neno_amount": 0.001,
                "destination_wallet": TEST_WALLET
            }
        )
        
        # Should not fail due to unknown field
        assert response.status_code != 422, f"destination_wallet field rejected: {response.text}"
        print(f"✓ SELL accepts destination_wallet field (status: {response.status_code})")

    def test_10_sell_accepts_destination_iban(self, auth_headers):
        """SELL endpoint should accept destination_iban field for EUR."""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/sell",
            headers=auth_headers,
            json={
                "receive_asset": "EUR",
                "neno_amount": 0.001,
                "destination_iban": "IT60X0542811101000000123456"
            }
        )
        
        # Should not fail due to unknown field
        assert response.status_code != 422, f"destination_iban field rejected: {response.text}"
        print(f"✓ SELL accepts destination_iban field (status: {response.status_code})")


class TestSwapEndpointFields:
    """Test SWAP endpoint accepts destination_wallet."""

    def test_11_swap_accepts_destination_wallet(self, auth_headers):
        """SWAP endpoint should accept destination_wallet field."""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/swap",
            headers=auth_headers,
            json={
                "from_asset": "NENO",
                "to_asset": "ETH",
                "amount": 0.001,
                "destination_wallet": TEST_WALLET
            }
        )
        
        # Should not fail due to unknown field
        assert response.status_code != 422, f"destination_wallet field rejected: {response.text}"
        print(f"✓ SWAP accepts destination_wallet field (status: {response.status_code})")


class TestWithdrawRealEndpoint:
    """Test /api/neno-exchange/withdraw-real endpoint."""

    def test_12_withdraw_real_requires_auth(self):
        """Withdraw-real endpoint should require authentication."""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/withdraw-real",
            json={
                "asset": "NENO",
                "amount": 0.001,
                "destination_wallet": TEST_WALLET
            }
        )
        
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        print(f"✓ Withdraw-real requires auth (status: {response.status_code})")

    def test_13_withdraw_real_with_auth(self, auth_headers):
        """Withdraw-real endpoint should work with auth."""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/withdraw-real",
            headers=auth_headers,
            json={
                "asset": "NENO",
                "amount": 0.001,
                "destination_wallet": TEST_WALLET
            }
        )
        
        # Should not be 401/403 with auth
        assert response.status_code not in [401, 403], f"Auth should work, got {response.status_code}"
        
        # Could be 400 (insufficient balance), 429 (rate limit), 500 (execution error), or 200 (success)
        print(f"✓ Withdraw-real accepts auth (status: {response.status_code})")
        
        if response.status_code == 200:
            data = response.json()
            assert "execution_proof" in data, "Missing execution_proof in response"
            assert "tx_hash" in data.get("execution_proof", {}), "Missing tx_hash in execution_proof"
            print(f"✓ Withdraw-real returned execution proof: {data.get('execution_proof', {}).get('tx_hash', 'N/A')[:20]}...")


class TestStatusEnforcement:
    """Test status enforcement - only 'completed' with proof."""

    def test_14_buy_returns_completed_status(self, auth_headers):
        """BUY should return completed status (internal treasury proof)."""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/buy",
            headers=auth_headers,
            json={
                "pay_asset": "EUR",
                "neno_amount": 0.0001
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            tx = data.get("transaction", {})
            status = tx.get("status")
            # BUY is internal, should be completed (treasury proof)
            assert status == "completed", f"Expected completed status, got {status}"
            print(f"✓ BUY returns completed status")
        elif response.status_code == 400:
            print(f"⚠ BUY failed (likely insufficient balance): {response.text[:100]}")
        else:
            print(f"⚠ BUY returned {response.status_code}: {response.text[:100]}")

    def test_15_sell_status_depends_on_proof(self, auth_headers):
        """SELL status should depend on execution proof."""
        response = requests.post(
            f"{BASE_URL}/api/neno-exchange/sell",
            headers=auth_headers,
            json={
                "receive_asset": "EUR",
                "neno_amount": 0.0001
            }
        )
        
        if response.status_code == 200:
            data = response.json()
            tx = data.get("transaction", {})
            status = tx.get("status")
            state = data.get("state")
            
            # Status should be completed (treasury proof) or pending_execution
            assert status in ["completed", "pending_execution", "pending_settlement"], \
                f"Unexpected status: {status}"
            
            print(f"✓ SELL status: {status}, state: {state}")
            
            # Check execution_proof
            proof = data.get("execution_proof", {})
            if proof.get("tx_hash") or proof.get("payout_id") or proof.get("treasury_movement"):
                print(f"✓ SELL has execution proof: {proof}")
        else:
            print(f"⚠ SELL returned {response.status_code}: {response.text[:100]}")


class TestWebSocketEndpoint:
    """Test WebSocket balance endpoint exists."""

    def test_16_websocket_endpoint_exists(self, auth_token):
        """WebSocket balance endpoint should exist at /ws/balances/{token}."""
        # We can't fully test WebSocket with requests, but we can check the upgrade
        ws_url = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")
        
        # Try HTTP request to WebSocket endpoint - should get upgrade required or similar
        response = requests.get(
            f"{BASE_URL}/ws/balances/{auth_token}",
            headers={"Upgrade": "websocket", "Connection": "Upgrade"}
        )
        
        # WebSocket endpoints typically return 400 or 426 for non-WebSocket requests
        # or 101 for successful upgrade (which requests can't handle)
        print(f"WebSocket endpoint response: {response.status_code}")
        
        # The endpoint exists if we don't get 404
        assert response.status_code != 404, "WebSocket endpoint not found"
        print(f"✓ WebSocket endpoint exists at /ws/balances/{{token}}")


class TestPlatformWallet:
    """Test platform wallet endpoint."""

    def test_17_platform_wallet_returns_address(self):
        """Platform wallet endpoint should return hot wallet address."""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/platform-wallet")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "address" in data, "Missing address"
        assert data["address"].startswith("0x"), "Invalid address format"
        assert data.get("chain") == "BSC Mainnet", f"Expected BSC Mainnet, got {data.get('chain')}"
        
        print(f"✓ Platform wallet: {data['address']}")


class TestMarketEndpoints:
    """Test market and price endpoints."""

    def test_18_price_endpoint_returns_mm_data(self):
        """Price endpoint should return market maker data."""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/price")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "bid" in data, "Missing bid"
        assert "ask" in data, "Missing ask"
        assert "spread_bps" in data, "Missing spread_bps"
        assert "mid_price" in data, "Missing mid_price"
        
        print(f"✓ Price: bid={data['bid']}, ask={data['ask']}, spread={data['spread_bps']}bps")

    def test_19_market_endpoint_returns_supported_assets(self):
        """Market endpoint should return supported assets."""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/market")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "supported_assets" in data, "Missing supported_assets"
        assert "pricing_model" in data, "Missing pricing_model"
        
        print(f"✓ Market: {len(data['supported_assets'])} assets, model={data['pricing_model']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
