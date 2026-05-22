#!/usr/bin/env python3
"""
E2E Test Script for NeoNoble Ramp Platform

This script tests the complete flow of the platform including:
1. User signup/login
2. Developer signup/login
3. API key creation
4. HMAC-protected ramp API endpoints
5. Quote generation with real prices and fixed NENO price

Usage:
    python scripts/e2e_test.py
    
    # Or with custom API URL:
    API_URL=https://multi-chain-wallet-14.preview.emergentagent.com/api python scripts/e2e_test.py

Requirements:
    pip install requests
"""

import requests
import json
import hmac
import hashlib
import time
import sys
import os

# Use environment variable or default to production URL
BASE_URL = os.environ.get('API_URL', 'https://multi-chain-wallet-14.preview.emergentagent.com/api')

# Colors for output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def log_success(msg):
    print(f"{GREEN}✓ {msg}{RESET}")

def log_error(msg):
    print(f"{RED}✗ {msg}{RESET}")

def log_info(msg):
    print(f"{YELLOW}→ {msg}{RESET}")

def generate_hmac_signature(timestamp: str, body_json: str, secret: str) -> str:
    message = f"{timestamp}{body_json}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()

def make_hmac_request(endpoint: str, data: dict, api_key: str, api_secret: str):
    timestamp = str(int(time.time()))
    body_json = json.dumps(data)
    signature = generate_hmac_signature(timestamp, body_json, api_secret)
    
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": api_key,
        "X-TIMESTAMP": timestamp,
        "X-SIGNATURE": signature
    }
    
    response = requests.post(f"{BASE_URL}{endpoint}", headers=headers, data=body_json)
    return response

def test_health():
    """Test health endpoints"""
    print("\n" + "="*50)
    print("TESTING HEALTH ENDPOINTS")
    print("="*50)
    
    # Basic health
    response = requests.get(f"{BASE_URL}/health")
    if response.status_code == 200:
        log_success("Health endpoint OK")
    else:
        log_error(f"Health endpoint failed: {response.status_code}")
        return False
    
    # Ramp API health
    response = requests.get(f"{BASE_URL}/ramp-api-health")
    if response.status_code == 200:
        data = response.json()
        log_success(f"Ramp API health OK - {len(data['supported_cryptos'])} supported cryptos")
        log_info(f"NENO fixed price: €{data['neno_price_eur']}")
    else:
        log_error(f"Ramp API health failed: {response.status_code}")
        return False
    
    return True

def test_user_auth():
    """Test user signup and login"""
    print("\n" + "="*50)
    print("TESTING USER AUTHENTICATION")
    print("="*50)
    
    email = f"e2e_user_{int(time.time())}@test.com"
    password = "TestPass123!"
    
    # Signup
    response = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": password,
        "role": "USER"
    })
    
    if response.status_code == 200:
        data = response.json()
        log_success(f"User signup OK: {email}")
        log_info(f"User ID: {data['user']['id']}")
        token = data['token']
    else:
        log_error(f"User signup failed: {response.json()}")
        return None, None
    
    # Login
    response = requests.post(f"{BASE_URL}/auth/login", json={
        "email": email,
        "password": password
    })
    
    if response.status_code == 200:
        log_success("User login OK")
    else:
        log_error(f"User login failed: {response.json()}")
        return None, None
    
    # Get current user
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BASE_URL}/auth/me", headers=headers)
    
    if response.status_code == 200:
        log_success("Get current user OK")
    else:
        log_error(f"Get current user failed: {response.status_code}")
    
    return token, email

def test_developer_auth():
    """Test developer signup and login"""
    print("\n" + "="*50)
    print("TESTING DEVELOPER AUTHENTICATION")
    print("="*50)
    
    email = f"e2e_dev_{int(time.time())}@test.com"
    password = "DevPass123!"
    
    # Signup as developer
    response = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": password,
        "role": "DEVELOPER"
    })
    
    if response.status_code == 200:
        data = response.json()
        log_success(f"Developer signup OK: {email}")
        log_info(f"Role: {data['user']['role']}")
        token = data['token']
    else:
        log_error(f"Developer signup failed: {response.json()}")
        return None
    
    return token

def test_api_key_creation(dev_token):
    """Test API key creation"""
    print("\n" + "="*50)
    print("TESTING API KEY CREATION")
    print("="*50)
    
    headers = {"Authorization": f"Bearer {dev_token}"}
    
    # Create API key
    response = requests.post(f"{BASE_URL}/dev/api-keys", headers=headers, json={
        "name": "E2E Test Key",
        "description": "Created during E2E testing",
        "rate_limit": 1000
    })
    
    if response.status_code == 200:
        data = response.json()
        log_success("API key created successfully")
        log_info(f"API Key: {data['api_key']}")
        log_info(f"API Secret: {data['api_secret'][:20]}... (truncated)")
        return data['api_key'], data['api_secret']
    else:
        log_error(f"API key creation failed: {response.json()}")
        return None, None

def test_hmac_endpoints(api_key, api_secret):
    """Test HMAC-protected ramp API endpoints"""
    print("\n" + "="*50)
    print("TESTING HMAC-PROTECTED RAMP API")
    print("="*50)
    
    # Test onramp quote for BTC
    log_info("Testing onramp quote (100 EUR -> BTC)")
    response = make_hmac_request("/ramp-api-onramp-quote", {
        "fiat_amount": 100,
        "crypto_currency": "BTC"
    }, api_key, api_secret)
    
    if response.status_code == 200:
        data = response.json()
        log_success(f"BTC onramp quote OK - Rate: €{data['exchange_rate']:,.0f}")
        log_info(f"100 EUR = {data['crypto_amount']:.8f} BTC")
        log_info(f"Price source: {data['price_source']}")
    else:
        log_error(f"BTC onramp quote failed: {response.json()}")
        return False
    
    # Test onramp quote for NENO (fixed price)
    log_info("\nTesting NENO onramp quote (10000 EUR -> NENO)")
    response = make_hmac_request("/ramp-api-onramp-quote", {
        "fiat_amount": 10000,
        "crypto_currency": "NENO"
    }, api_key, api_secret)
    
    if response.status_code == 200:
        data = response.json()
        if data['exchange_rate'] == 10000.0 and data['crypto_amount'] == 1.0:
            log_success(f"NENO onramp quote OK - Fixed rate: €{data['exchange_rate']:,.0f}")
            log_info(f"10000 EUR = {data['crypto_amount']} NENO (✓ correct)")
            log_info(f"Price source: {data['price_source']} (should be 'fixed')")
        else:
            log_error(f"NENO price mismatch! Expected 1.0 NENO, got {data['crypto_amount']}")
            return False
    else:
        log_error(f"NENO onramp quote failed: {response.json()}")
        return False
    
    # Test offramp quote for NENO
    log_info("\nTesting NENO offramp quote (0.5 NENO -> EUR)")
    response = make_hmac_request("/ramp-api-offramp-quote", {
        "crypto_amount": 0.5,
        "crypto_currency": "NENO"
    }, api_key, api_secret)
    
    if response.status_code == 200:
        data = response.json()
        expected_fiat = 5000.0  # 0.5 * 10000
        if data['fiat_amount'] == expected_fiat:
            log_success(f"NENO offramp quote OK")
            log_info(f"0.5 NENO = €{data['fiat_amount']:,.0f} (before fee)")
            log_info(f"Fee: €{data['fee_amount']} ({data['fee_percentage']}%)")
            log_info(f"You receive: €{data['total_fiat']:,.0f}")
        else:
            log_error(f"NENO offramp mismatch! Expected €{expected_fiat}, got €{data['fiat_amount']}")
            return False
    else:
        log_error(f"NENO offramp quote failed: {response.json()}")
        return False
    
    # Test replay protection (wrong timestamp)
    log_info("\nTesting replay protection (old timestamp)")
    old_timestamp = str(int(time.time()) - 600)  # 10 minutes ago
    body_json = json.dumps({"fiat_amount": 100, "crypto_currency": "BTC"})
    signature = generate_hmac_signature(old_timestamp, body_json, api_secret)
    
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": api_key,
        "X-TIMESTAMP": old_timestamp,
        "X-SIGNATURE": signature
    }
    
    response = requests.post(f"{BASE_URL}/ramp-api-onramp-quote", headers=headers, data=body_json)
    
    if response.status_code == 401:
        log_success("Replay protection working - old timestamp rejected")
    else:
        log_error(f"Replay protection failed - should have rejected old timestamp")
        return False
    
    # Test invalid signature
    log_info("\nTesting invalid signature rejection")
    timestamp = str(int(time.time()))
    
    headers = {
        "Content-Type": "application/json",
        "X-API-KEY": api_key,
        "X-TIMESTAMP": timestamp,
        "X-SIGNATURE": "invalid_signature_here"
    }
    
    response = requests.post(f"{BASE_URL}/ramp-api-onramp-quote", headers=headers, data=body_json)
    
    if response.status_code == 401:
        log_success("Invalid signature rejected correctly")
    else:
        log_error(f"Should have rejected invalid signature")
        return False
    
    return True

def test_user_ramp_flow(user_token):
    """Test user-facing ramp endpoints"""
    print("\n" + "="*50)
    print("TESTING USER RAMP FLOW")
    print("="*50)
    
    headers = {"Authorization": f"Bearer {user_token}"}
    
    # Get prices
    response = requests.get(f"{BASE_URL}/ramp/prices")
    if response.status_code == 200:
        data = response.json()
        log_success(f"Prices fetched - {len(data['prices'])} currencies")
        log_info(f"NENO price: €{data['prices'].get('NENO', 'N/A')}")
    else:
        log_error(f"Failed to get prices: {response.status_code}")
    
    # Create onramp quote
    response = requests.post(f"{BASE_URL}/ramp/onramp/quote", headers=headers, json={
        "fiat_amount": 500,
        "crypto_currency": "ETH"
    })
    
    if response.status_code == 200:
        data = response.json()
        log_success(f"User onramp quote created")
        log_info(f"500 EUR = {data['crypto_amount']:.6f} ETH")
        quote_id = data['quote_id']
        
        # Execute onramp
        response = requests.post(f"{BASE_URL}/ramp/onramp/execute", headers=headers, json={
            "quote_id": quote_id,
            "wallet_address": "0x1234567890123456789012345678901234567890"
        })
        
        if response.status_code == 200:
            data = response.json()
            log_success(f"Onramp transaction executed")
            log_info(f"Reference: {data['reference']}")
            log_info(f"Status: {data['status']}")
        else:
            log_error(f"Onramp execution failed: {response.json()}")
    else:
        log_error(f"User onramp quote failed: {response.json()}")
    
    # Get transaction history
    response = requests.get(f"{BASE_URL}/ramp/transactions", headers=headers)
    if response.status_code == 200:
        data = response.json()
        log_success(f"Transaction history fetched - {len(data)} transactions")
    else:
        log_error(f"Failed to get transactions: {response.status_code}")
    
    return True

def main():
    print("\n" + "="*60)
    print("  NEONOBLE RAMP E2E TEST SUITE")
    print("="*60)
    
    all_passed = True
    
    # Test 1: Health endpoints
    if not test_health():
        all_passed = False
    
    # Test 2: User authentication
    user_token, user_email = test_user_auth()
    if not user_token:
        all_passed = False
    
    # Test 3: Developer authentication
    dev_token = test_developer_auth()
    if not dev_token:
        all_passed = False
    
    # Test 4: API key creation
    if dev_token:
        api_key, api_secret = test_api_key_creation(dev_token)
        if not api_key:
            all_passed = False
    else:
        api_key, api_secret = None, None
    
    # Test 5: HMAC endpoints
    if api_key and api_secret:
        if not test_hmac_endpoints(api_key, api_secret):
            all_passed = False
    
    # Test 6: User ramp flow
    if user_token:
        if not test_user_ramp_flow(user_token):
            all_passed = False
    
    # Summary
    print("\n" + "="*60)
    if all_passed:
        print(f"{GREEN}  ALL TESTS PASSED!{RESET}")
    else:
        print(f"{RED}  SOME TESTS FAILED!{RESET}")
    print("="*60 + "\n")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
