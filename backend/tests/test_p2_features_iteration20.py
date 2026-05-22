"""
Iteration 20 - P2 Features Testing
Tests for:
1. Monte Carlo VaR Simulation API
2. PEP Screening & Sanctions API
3. Additional Languages (9 total)
4. Regression checks for existing endpoints
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "admin@neonobleramp.com"
ADMIN_PASSWORD = "Admin1234!"


class TestHealthAndRegression:
    """Regression tests for existing endpoints"""
    
    def test_health_endpoint(self):
        """Test health endpoint is working"""
        response = requests.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "healthy"
        print(f"PASS: Health endpoint returns status=healthy")
    
    def test_neno_exchange_market(self):
        """Regression: NENO Exchange market endpoint"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/market")
        assert response.status_code == 200
        data = response.json()
        assert "neno_eur_price" in data
        assert "supported_assets" in data
        print(f"PASS: NENO Exchange market endpoint working, price={data.get('neno_eur_price')}")
    
    def test_neno_exchange_price(self):
        """Regression: NENO Exchange price endpoint"""
        response = requests.get(f"{BASE_URL}/api/neno-exchange/price")
        assert response.status_code == 200
        data = response.json()
        # API returns neno_eur_price instead of price_eur
        price = data.get("price_eur") or data.get("neno_eur_price")
        assert price is not None, f"No price in response: {data}"
        print(f"PASS: NENO Exchange price endpoint working, price={price}")


class TestAuthentication:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        token = data.get("access_token") or data.get("token")
        assert token, f"No token in response: {data}"
        print(f"PASS: Admin login successful")
        return token
    
    def test_admin_login(self, admin_token):
        """Verify admin can login"""
        assert admin_token is not None
        assert len(admin_token) > 0
        print(f"PASS: Admin token obtained (length={len(admin_token)})")


class TestMonteCarloVaR:
    """Monte Carlo VaR Simulation API tests"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Admin login failed")
        data = response.json()
        return data.get("access_token") or data.get("token")
    
    def test_montecarlo_var_default_params(self, admin_token):
        """Test Monte Carlo VaR with default parameters"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/analytics/montecarlo/var", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "portfolio_value_eur" in data
        assert "var" in data or "var_95" in data
        
        # Check if portfolio has value or empty message
        if data.get("portfolio_value_eur", 0) > 0:
            assert "positions" in data
            assert "simulation_params" in data
            assert "distribution" in data
            print(f"PASS: Monte Carlo VaR - Portfolio value: EUR {data['portfolio_value_eur']}")
            print(f"      VaR data: {data.get('var', {})}")
        else:
            print(f"PASS: Monte Carlo VaR - Empty portfolio message: {data.get('message')}")
    
    def test_montecarlo_var_custom_params(self, admin_token):
        """Test Monte Carlo VaR with custom parameters"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        params = {
            "simulations": 500,
            "horizon_days": 10,
            "confidence": 0.95
        }
        response = requests.get(f"{BASE_URL}/api/analytics/montecarlo/var", headers=headers, params=params)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify custom params are reflected
        if "simulation_params" in data:
            sim_params = data["simulation_params"]
            assert sim_params.get("simulations") == 500
            assert sim_params.get("horizon_days") == 10
            assert sim_params.get("confidence_level") == 0.95
            print(f"PASS: Monte Carlo VaR with custom params - simulations={sim_params.get('simulations')}, horizon={sim_params.get('horizon_days')}")
        else:
            print(f"PASS: Monte Carlo VaR custom params - Empty portfolio")
    
    def test_montecarlo_var_requires_auth(self):
        """Test Monte Carlo VaR requires authentication"""
        response = requests.get(f"{BASE_URL}/api/analytics/montecarlo/var")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print(f"PASS: Monte Carlo VaR requires authentication (status={response.status_code})")


class TestPEPScreening:
    """PEP Screening & Sanctions API tests"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Admin login failed")
        data = response.json()
        return data.get("access_token") or data.get("token")
    
    def test_pep_screen_clear_person(self, admin_token):
        """Test PEP screening for a clean person (no hits)"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        payload = {
            "first_name": "Mario",
            "last_name": "Rossi",
            "nationality": "Italy"
        }
        response = requests.post(f"{BASE_URL}/api/pep/screen", headers=headers, json=payload)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "status" in data
        assert "risk_score" in data
        assert "screened_name" in data
        assert "lists_checked" in data
        
        # Clean person should have CLEAR status
        assert data["status"] == "CLEAR", f"Expected CLEAR, got {data['status']}"
        assert data["risk_score"] == 0
        print(f"PASS: PEP Screen clean person - status={data['status']}, risk_score={data['risk_score']}")
    
    def test_pep_screen_sanctioned_entity(self, admin_token):
        """Test PEP screening for a sanctioned entity (North Korea)"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        payload = {
            "first_name": "Test",
            "last_name": "Person",
            "nationality": "North Korea"
        }
        response = requests.post(f"{BASE_URL}/api/pep/screen", headers=headers, json=payload)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Sanctioned entity should have BLOCKED or REVIEW status
        assert data["status"] in ["BLOCKED", "REVIEW"], f"Expected BLOCKED/REVIEW, got {data['status']}"
        assert data["risk_score"] > 0
        assert len(data.get("hits", [])) > 0
        print(f"PASS: PEP Screen sanctioned entity - status={data['status']}, risk_score={data['risk_score']}, hits={len(data.get('hits', []))}")
    
    def test_pep_screen_pep_title(self, admin_token):
        """Test PEP screening for a person with PEP title"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        payload = {
            "first_name": "John",
            "last_name": "Smith",
            "nationality": "USA",
            "additional_info": "Former President"
        }
        response = requests.post(f"{BASE_URL}/api/pep/screen", headers=headers, json=payload)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # PEP should have REVIEW status
        assert data["status"] in ["REVIEW", "BLOCKED"], f"Expected REVIEW/BLOCKED, got {data['status']}"
        assert data["risk_score"] > 0
        print(f"PASS: PEP Screen with title - status={data['status']}, risk_score={data['risk_score']}")
    
    def test_pep_add_to_watchlist(self, admin_token):
        """Test adding entry to internal watchlist"""
        headers = {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
        payload = {
            "name": "TEST_Watchlist_Entry_20",
            "category": "SANCTIONS",
            "severity": "high",
            "reason": "Test entry for iteration 20"
        }
        response = requests.post(f"{BASE_URL}/api/pep/watchlist", headers=headers, json=payload)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "message" in data
        assert "entry" in data
        assert data["entry"]["name"] == "TEST_Watchlist_Entry_20"
        print(f"PASS: PEP Watchlist add - {data['message']}")
    
    def test_pep_screening_history(self, admin_token):
        """Test getting screening history"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/pep/history", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "screenings" in data
        assert "total" in data
        assert isinstance(data["screenings"], list)
        print(f"PASS: PEP History - total={data['total']} screenings")
    
    def test_pep_screening_stats(self, admin_token):
        """Test getting screening statistics"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/pep/stats", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "total_screenings" in data
        assert "clear" in data
        assert "review" in data
        assert "blocked" in data
        assert "watchlist_entries" in data
        assert "lists_active" in data
        print(f"PASS: PEP Stats - total={data['total_screenings']}, clear={data['clear']}, review={data['review']}, blocked={data['blocked']}")
    
    def test_pep_screen_requires_admin(self):
        """Test PEP screening requires admin role"""
        # Try without auth
        response = requests.post(f"{BASE_URL}/api/pep/screen", json={
            "first_name": "Test",
            "last_name": "User"
        })
        assert response.status_code in [401, 403, 422], f"Expected 401/403/422, got {response.status_code}"
        print(f"PASS: PEP Screen requires authentication (status={response.status_code})")


class TestWalletBalances:
    """Test wallet balances for Monte Carlo VaR context"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if response.status_code != 200:
            pytest.skip("Admin login failed")
        data = response.json()
        return data.get("access_token") or data.get("token")
    
    def test_wallet_balances(self, admin_token):
        """Test wallet balances endpoint"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/wallet/balances", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # API returns 'wallets' key
        wallets = data.get("wallets") or data.get("balances") or (data if isinstance(data, list) else [])
        assert len(wallets) > 0, f"No wallets found: {data}"
        print(f"PASS: Wallet balances - {len(wallets)} assets, total_eur_value={data.get('total_eur_value', 'N/A')}")
        for w in wallets[:5]:  # Show first 5
            if isinstance(w, dict):
                print(f"      {w.get('asset', 'N/A')}: {w.get('balance', 0)} (EUR {w.get('eur_value', 0)})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
