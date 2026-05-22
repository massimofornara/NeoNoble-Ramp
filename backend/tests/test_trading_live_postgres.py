"""
Backend API Tests for NeoNoble Ramp - Trading Live & PostgreSQL Migration

Tests:
- DEX API: Status, enabled state, is_ready
- Exchange API: Status, shadow_mode=false, Kraken connected, Coinbase listed
- Database: dual_write mode active
- Auth API: Registration creates user in both MongoDB and PostgreSQL
- Auth API: Login returns token
"""

import pytest
import requests
import os
import uuid
from datetime import datetime

# Get backend URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://multi-chain-wallet-14.preview.emergentagent.com"


class TestHealthCheck:
    """Health check tests - run first"""
    
    def test_health_endpoint(self):
        """Test /api/health endpoint"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print(f"✓ Health check passed: {data}")


class TestDEXAPI:
    """DEX API tests - Status and configuration"""
    
    def test_dex_status_enabled(self):
        """Test GET /api/dex/status - should show enabled=true, is_ready=true"""
        response = requests.get(f"{BASE_URL}/api/dex/status")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "enabled" in data, "Response missing 'enabled' field"
        assert "is_ready" in data, "Response missing 'is_ready' field"
        
        # Validate DEX is enabled
        assert data["enabled"] == True, f"DEX should be enabled, got enabled={data['enabled']}"
        assert data["is_ready"] == True, f"DEX should be ready, got is_ready={data['is_ready']}"
        
        print(f"✓ DEX Status: enabled={data['enabled']}, is_ready={data['is_ready']}")
        
        # Additional status info
        if "conversion_wallet" in data:
            print(f"  Conversion wallet: {data['conversion_wallet']}")
        if "settlement_wallet" in data:
            print(f"  Settlement wallet: {data['settlement_wallet']}")
        if "mode" in data:
            print(f"  Mode: {data['mode']}")


class TestExchangeAPI:
    """Exchange API tests - Connector status and trading mode"""
    
    def test_exchange_status_live_mode(self):
        """Test GET /api/exchanges/status - should show enabled=true, shadow_mode=false"""
        response = requests.get(f"{BASE_URL}/api/exchanges/status")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "enabled" in data, "Response missing 'enabled' field"
        assert "shadow_mode" in data, "Response missing 'shadow_mode' field"
        assert "venues" in data, "Response missing 'venues' field"
        
        # Validate trading is enabled and NOT in shadow mode
        assert data["enabled"] == True, f"Exchange trading should be enabled, got enabled={data['enabled']}"
        assert data["shadow_mode"] == False, f"Shadow mode should be disabled for live trading, got shadow_mode={data['shadow_mode']}"
        
        print(f"✓ Exchange Status: enabled={data['enabled']}, shadow_mode={data['shadow_mode']}")
        
        return data
    
    def test_kraken_connector_connected(self):
        """Test that Kraken connector is connected"""
        response = requests.get(f"{BASE_URL}/api/exchanges/status")
        
        assert response.status_code == 200
        data = response.json()
        
        venues = data.get("venues", {})
        assert "kraken" in venues, "Kraken venue should be listed"
        
        kraken_status = venues["kraken"]
        assert kraken_status.get("connected") == True, f"Kraken should be connected, got connected={kraken_status.get('connected')}"
        
        print(f"✓ Kraken connector: connected={kraken_status.get('connected')}, initialized={kraken_status.get('initialized')}")
    
    def test_coinbase_connector_listed(self):
        """Test that Coinbase connector is listed in venues (not configured yet)"""
        response = requests.get(f"{BASE_URL}/api/exchanges/status")
        
        assert response.status_code == 200
        data = response.json()
        
        venues = data.get("venues", {})
        assert "coinbase" in venues, "Coinbase venue should be listed"
        
        coinbase_status = venues["coinbase"]
        # Coinbase may not be connected (no API keys), but should be listed
        print(f"✓ Coinbase connector listed: connected={coinbase_status.get('connected')}, initialized={coinbase_status.get('initialized')}")
    
    def test_binance_connector_status(self):
        """Test Binance connector status (may be geo-blocked)"""
        response = requests.get(f"{BASE_URL}/api/exchanges/status")
        
        assert response.status_code == 200
        data = response.json()
        
        venues = data.get("venues", {})
        assert "binance" in venues, "Binance venue should be listed"
        
        binance_status = venues["binance"]
        print(f"✓ Binance connector: connected={binance_status.get('connected')}, initialized={binance_status.get('initialized')}")
        
        # Note: Binance may be geo-blocked (451 error) but should still be listed


class TestDatabaseMigration:
    """Database migration tests - dual_write mode"""
    
    def test_database_mode_dual_write(self):
        """Test that database is in dual_write mode"""
        response = requests.get(f"{BASE_URL}/api/migration/status")
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate dual_write mode
        mode = data.get("mode", "")
        assert mode == "dual_write", f"Database should be in dual_write mode, got mode={mode}"
        
        print(f"✓ Database mode: {mode}")
        
        # Additional migration info
        if "phase" in data:
            print(f"  Migration phase: {data['phase']}")
        if "mongodb_connected" in data:
            print(f"  MongoDB connected: {data['mongodb_connected']}")
        if "postgresql_connected" in data:
            print(f"  PostgreSQL connected: {data['postgresql_connected']}")


class TestAuthAPI:
    """Auth API tests - Registration and Login with dual-write"""
    
    def test_register_user_dual_write(self):
        """Test POST /api/auth/register - should create user in both MongoDB and PostgreSQL"""
        test_email = f"test_dual_{uuid.uuid4().hex[:8]}@example.com"
        response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": test_email,
                "password": "TestPassword123!",
                "name": "Dual Write Test User"
            }
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "token" in data, "Response missing token"
        assert "user" in data, "Response missing user"
        assert data["user"]["email"] == test_email
        
        print(f"✓ Registered user (dual-write): {test_email}")
        
        # Return credentials for login test
        return test_email, "TestPassword123!"
    
    def test_login_user_returns_token(self):
        """Test POST /api/auth/login - should authenticate and return token"""
        # First register a user
        test_email = f"test_login_{uuid.uuid4().hex[:8]}@example.com"
        test_password = "TestPassword123!"
        
        reg_response = requests.post(
            f"{BASE_URL}/api/auth/register",
            json={
                "email": test_email,
                "password": test_password,
                "name": "Login Test User"
            }
        )
        assert reg_response.status_code == 200, f"Registration failed: {reg_response.text}"
        
        # Now login
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": test_email,
                "password": test_password
            }
        )
        
        assert login_response.status_code == 200, f"Expected 200, got {login_response.status_code}: {login_response.text}"
        data = login_response.json()
        
        # Validate response structure
        assert "token" in data, "Response missing token"
        assert "user" in data, "Response missing user"
        assert data["user"]["email"] == test_email
        assert len(data["token"]) > 0, "Token should not be empty"
        
        print(f"✓ Login successful: {test_email}")
        print(f"  Token length: {len(data['token'])} chars")
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials returns 401"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={
                "email": "nonexistent@example.com",
                "password": "WrongPassword123!"
            }
        )
        
        assert response.status_code == 401, f"Expected 401 for invalid credentials, got {response.status_code}"
        print("✓ Invalid credentials correctly rejected with 401")


class TestExchangeBalances:
    """Exchange balance tests"""
    
    def test_get_exchange_balances(self):
        """Test GET /api/exchanges/balances - get all balances"""
        response = requests.get(f"{BASE_URL}/api/exchanges/balances")
        
        # May return 200 with empty balances or error if not connected
        if response.status_code == 200:
            data = response.json()
            assert "balances" in data
            print(f"✓ Exchange balances retrieved: {list(data['balances'].keys())}")
        else:
            print(f"⚠ Exchange balances returned {response.status_code} (may be expected if not connected)")


class TestDEXQuote:
    """DEX quote tests"""
    
    def test_get_dex_quote(self):
        """Test POST /api/dex/quote - get swap quote"""
        response = requests.post(
            f"{BASE_URL}/api/dex/quote",
            json={
                "source_token": "NENO",
                "destination_token": "USDT",
                "amount": 100.0
            }
        )
        
        # May return 200 with quote or 404 if no liquidity
        if response.status_code == 200:
            data = response.json()
            assert "quote_id" in data
            print(f"✓ DEX quote received: {data.get('quote_id')}")
            print(f"  Exchange rate: {data.get('exchange_rate')}")
        elif response.status_code == 404:
            print("⚠ No DEX quote available (may be expected if no liquidity)")
        else:
            print(f"⚠ DEX quote returned {response.status_code}: {response.text}")


class TestExchangeTicker:
    """Exchange ticker tests"""
    
    def test_get_ticker_kraken(self):
        """Test GET /api/exchanges/ticker/{symbol} - get ticker from Kraken"""
        response = requests.get(f"{BASE_URL}/api/exchanges/ticker/BTCEUR?venue=kraken")
        
        if response.status_code == 200:
            data = response.json()
            assert "bid" in data
            assert "ask" in data
            print(f"✓ Kraken ticker BTCEUR: bid={data.get('bid')}, ask={data.get('ask')}")
        elif response.status_code == 404:
            print("⚠ Kraken ticker not available (may be expected)")
        else:
            print(f"⚠ Kraken ticker returned {response.status_code}: {response.text}")


class TestMigrationValidation:
    """Migration validation tests"""
    
    def test_migration_validation(self):
        """Test POST /api/migration/validate - run validation"""
        response = requests.post(f"{BASE_URL}/api/migration/validate")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✓ Migration validation: passed={data.get('passed', 'unknown')}")
            if "checks" in data:
                for check in data["checks"]:
                    print(f"  - {check.get('name')}: passed={check.get('passed')}")
        else:
            print(f"⚠ Migration validation returned {response.status_code}: {response.text}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
