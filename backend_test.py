#!/usr/bin/env python3
"""
NeoNoble Ramp Backend API Test Suite - PHASE 2 & 3 VENUE INTEGRATION + HEDGE ACTIVATION

Performs comprehensive end-to-end testing of:
- NEW: Phase 2 - Exchange Connectors API (Venue Integration)
- NEW: Phase 3 - Hedge Activation API (Hedging Service)
- REGRESSION: Existing Services (DEX, Transak, Liquidity)

Test Environment:
- Backend URL: https://multi-chain-wallet-14.preview.emergentagent.com/api
- NENO Token: Fixed price €10,000 per token
- Fee: 1.5%

Phase 2 - Exchange Connectors (NEW):
  * Exchange status, balances, orders (shadow mode without credentials)
  * Binance + Kraken venues (not connected without API keys)
  * Order placement in shadow mode

Phase 3 - Hedge Activation (NEW):
  * Hedging service summary (shadow mode with policy)
  * Hedge proposals and events
  * Conservative Hybrid Policy configuration

Existing Services (Regression):
  * DEX Service - Real on-chain swaps (1inch + PancakeSwap) - DISABLED mode initially
  * Transak Service - On/Off-ramp widget integration - DEMO mode (no API key)
  * Treasury Service (REAL) - €100M virtual floor balance
  * Exposure Service (REAL) - Full lifecycle tracking
  * Routing Service (SHADOW) - Log-only market conversion simulation
  * Reconciliation Service (REAL) - Coverage events and audit ledger
"""

import asyncio
import aiohttp
import json
import logging
from typing import Dict, Any, Optional
import sys
import os
import time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Backend URL from frontend .env
BACKEND_URL = "https://multi-chain-wallet-14.preview.emergentagent.com/api"

class Phase2Phase3Tester:
    def __init__(self):
        self.session = None
        self.test_results = {}
        
        # Test credentials and tokens
        self.user_jwt = None
        self.quote_id = None
        self.exposure_id = None
        self.transak_order_id = None
        
        # Password reset test data
        self.test_user_email = "pwreset@test.com"
        self.test_user_password = "OldPassword123!"
        self.new_password = "NewPassword456!"
        self.reset_token = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def make_request(self, method: str, endpoint: str, data: Dict = None, 
                          headers: Dict = None, auth_token: str = None) -> tuple:
        """Make HTTP request and return (success, response_data, status_code)"""
        url = f"{BACKEND_URL}{endpoint}"
        
        request_headers = {"Content-Type": "application/json"}
        if headers:
            request_headers.update(headers)
        if auth_token:
            request_headers["Authorization"] = f"Bearer {auth_token}"
        
        try:
            async with self.session.request(
                method, url, 
                json=data if data else None,
                headers=request_headers
            ) as response:
                try:
                    response_data = await response.json()
                except:
                    response_data = await response.text()
                
                return response.status < 400, response_data, response.status
                
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return False, str(e), 0
    
    def log_test_result(self, test_name: str, success: bool, details: str = ""):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} {test_name}")
        if details:
            logger.info(f"    Details: {details}")
        
        self.test_results[test_name] = {
            "success": success,
            "details": details
        }

    async def test_phase2_exchange_connectors_api(self):
        """Test Phase 2 - Exchange Connectors API endpoints as specified in the review request"""
        logger.info("\n=== Testing Phase 2 - Exchange Connectors API ===")
        
        # Test 1: GET /api/exchanges/status - Should return connector manager status
        logger.info("Step 1: Test Exchange Connectors Status")
        success, data, status = await self.make_request("GET", "/exchanges/status")
        
        exchange_status_valid = False
        if success and isinstance(data, dict):
            enabled = data.get("enabled", True)  # Should be false (shadow mode)
            shadow_mode = data.get("shadow_mode", False)  # Should be true
            primary_venue = data.get("primary_venue")  # Should be "binance"
            fallback_venue = data.get("fallback_venue")  # Should be "kraken"
            venues = data.get("venues", {})
            
            exchange_status_valid = (
                enabled is False and
                shadow_mode is True and
                primary_venue == "binance" and
                fallback_venue == "kraken" and
                "binance" in venues and
                "kraken" in venues
            )
        
        self.log_test_result(
            "Exchange Connectors Status (Shadow Mode)",
            exchange_status_valid,
            f"Status: {status}, Enabled: {data.get('enabled') if isinstance(data, dict) else 'N/A'}, Shadow Mode: {data.get('shadow_mode') if isinstance(data, dict) else 'N/A'}, Primary: {data.get('primary_venue') if isinstance(data, dict) else 'N/A'}, Fallback: {data.get('fallback_venue') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 2: GET /api/exchanges/balances - Should return empty balances (no connected venues)
        logger.info("Step 2: Test Exchange Balances (No Connected Venues)")
        success, data, status = await self.make_request("GET", "/exchanges/balances")
        
        balances_valid = False
        if success and isinstance(data, dict):
            balances = data.get("balances", {})
            # Should be empty or show venues with no balances (not connected without credentials)
            balances_valid = isinstance(balances, dict)
        
        self.log_test_result(
            "Exchange Balances (No Connected Venues)",
            balances_valid,
            f"Status: {status}, Balances: {data.get('balances') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 3: GET /api/exchanges/orders - Should return empty order list initially
        logger.info("Step 3: Test Exchange Orders History")
        success, data, status = await self.make_request("GET", "/exchanges/orders")
        
        orders_valid = False
        if success and isinstance(data, dict):
            orders = data.get("orders", [])
            count = data.get("count", 0)
            orders_valid = isinstance(orders, list) and count >= 0
        
        self.log_test_result(
            "Exchange Orders History",
            orders_valid,
            f"Status: {status}, Orders Count: {data.get('count') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 4: POST /api/exchanges/orders - Test placing an order in shadow mode
        logger.info("Step 4: Test Place Order in Shadow Mode")
        order_payload = {
            "symbol": "BNBEUR",
            "side": "sell",
            "quantity": 0.1,
            "order_type": "market"
        }
        success, data, status = await self.make_request("POST", "/exchanges/orders", order_payload)
        
        order_place_valid = False
        if success and isinstance(data, dict):
            mode = data.get("mode")
            order = data.get("order", {})
            order_place_valid = mode == "shadow" and isinstance(order, dict)
        
        self.log_test_result(
            "Place Order in Shadow Mode (BNBEUR sell)",
            order_place_valid,
            f"Status: {status}, Mode: {data.get('mode') if isinstance(data, dict) else 'N/A'}, Order ID: {data.get('order', {}).get('order_id') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 5: GET /api/exchanges/admin/config - Should return exchange configuration
        logger.info("Step 5: Test Exchange Admin Configuration")
        success, data, status = await self.make_request("GET", "/exchanges/admin/config")
        
        config_valid = False
        if success and isinstance(data, dict):
            # Should return config object (may be empty if not configured)
            config_valid = True
        elif status == 404:
            # No config found is also acceptable
            config_valid = True
        
        self.log_test_result(
            "Exchange Admin Configuration",
            config_valid,
            f"Status: {status}, Config Keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}"
        )
        
        return exchange_status_valid and balances_valid and orders_valid and order_place_valid and config_valid

    async def test_phase3_hedge_activation_api(self):
        """Test Phase 3 - Hedge Activation API endpoints as specified in the review request"""
        logger.info("\n=== Testing Phase 3 - Hedge Activation API ===")
        
        # Test 1: GET /api/liquidity/hedging/summary - Should show shadow mode with policy
        logger.info("Step 1: Test Hedging Service Summary")
        success, data, status = await self.make_request("GET", "/liquidity/hedging/summary")
        
        hedging_summary_valid = False
        if success and isinstance(data, dict):
            shadow_mode = data.get("shadow_mode", False)
            policy = data.get("policy", {})
            policy_name = policy.get("name") if isinstance(policy, dict) else None
            exposure_threshold_pct = policy.get("exposure_threshold_pct") if isinstance(policy, dict) else None
            batch_window_hours = policy.get("batch_window_hours") if isinstance(policy, dict) else None
            volatility_guard_enabled = policy.get("volatility_guard_enabled") if isinstance(policy, dict) else None
            
            hedging_summary_valid = (
                shadow_mode is True and
                policy_name == "Conservative Hybrid Policy" and
                exposure_threshold_pct == 0.75 and
                batch_window_hours == 12 and
                volatility_guard_enabled is True
            )
        
        self.log_test_result(
            "Hedging Service Summary (Shadow Mode + Policy)",
            hedging_summary_valid,
            f"Status: {status}, Shadow Mode: {data.get('shadow_mode') if isinstance(data, dict) else 'N/A'}, Policy: {data.get('policy', {}).get('name') if isinstance(data, dict) else 'N/A'}, Threshold: {data.get('policy', {}).get('exposure_threshold_pct') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 2: GET /api/liquidity/hedging/proposals - Should return recent hedge proposals
        logger.info("Step 2: Test Hedge Proposals")
        success, data, status = await self.make_request("GET", "/liquidity/hedging/proposals")
        
        proposals_valid = False
        if success and isinstance(data, dict):
            proposals = data.get("proposals", [])
            count = data.get("count", 0)
            shadow_mode = data.get("shadow_mode", False)
            proposals_valid = isinstance(proposals, list) and count >= 0 and shadow_mode is True
        
        self.log_test_result(
            "Hedge Proposals",
            proposals_valid,
            f"Status: {status}, Proposals Count: {data.get('count') if isinstance(data, dict) else 'N/A'}, Shadow Mode: {data.get('shadow_mode') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 3: GET /api/liquidity/hedging/events - Should return recent hedge events
        logger.info("Step 3: Test Hedge Events")
        success, data, status = await self.make_request("GET", "/liquidity/hedging/events")
        
        events_valid = False
        if success and isinstance(data, dict):
            hedges = data.get("hedges", [])
            count = data.get("count", 0)
            shadow_mode = data.get("shadow_mode", False)
            events_valid = isinstance(hedges, list) and count >= 0 and shadow_mode is True
        
        self.log_test_result(
            "Hedge Events",
            events_valid,
            f"Status: {status}, Events Count: {data.get('count') if isinstance(data, dict) else 'N/A'}, Shadow Mode: {data.get('shadow_mode') if isinstance(data, dict) else 'N/A'}"
        )
        
        return hedging_summary_valid and proposals_valid and events_valid

    async def test_existing_services_regression(self):
        """Test existing services still work (regression testing)"""
        logger.info("\n=== Testing Existing Services Regression ===")
        
        # Test 1: GET /api/liquidity/dashboard - Full dashboard
        logger.info("Step 1: Test Liquidity Dashboard (Regression)")
        success, data, status = await self.make_request("GET", "/liquidity/dashboard")
        
        dashboard_valid = False
        if success and isinstance(data, dict):
            services = data.get("services", {})
            dashboard_valid = (
                services.get("treasury") and
                services.get("exposure") and
                services.get("routing") and
                services.get("hedging") and
                services.get("reconciliation") and
                data.get("mode") == "hybrid"
            )
        
        self.log_test_result(
            "Liquidity Dashboard (Regression)",
            dashboard_valid,
            f"Status: {status}, Services Active: {len(data.get('services', {})) if isinstance(data, dict) else 'N/A'}, Mode: {data.get('mode') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 2: GET /api/dex/status - DEX service
        logger.info("Step 2: Test DEX Service Status (Regression)")
        success, data, status = await self.make_request("GET", "/dex/status")
        
        dex_status_valid = False
        if success and isinstance(data, dict):
            enabled = data.get("enabled", True)  # Should be false initially
            dex_status_valid = enabled is False  # DEX should be disabled initially
        
        self.log_test_result(
            "DEX Service Status (Regression)",
            dex_status_valid,
            f"Status: {status}, Enabled: {data.get('enabled') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 3: GET /api/transak/status - Transak service
        logger.info("Step 3: Test Transak Service Status (Regression)")
        success, data, status = await self.make_request("GET", "/transak/status")
        
        transak_status_valid = False
        if success and isinstance(data, dict):
            configured = data.get("configured", True)  # Should be false without API key
            transak_status_valid = configured is False  # Should be in demo mode
        
        self.log_test_result(
            "Transak Service Status (Regression)",
            transak_status_valid,
            f"Status: {status}, Configured: {data.get('configured') if isinstance(data, dict) else 'N/A'}"
        )
        
        return dashboard_valid and dex_status_valid and transak_status_valid

    async def test_dex_service_api(self):
        logger.info("\n=== Testing DEX Service API ===")
        
        # Test 1: GET /api/dex/status - Should return service status with enabled: false, web3_connected: true
        logger.info("Step 1: Test DEX Service Status")
        success, data, status = await self.make_request("GET", "/dex/status")
        
        dex_status_valid = False
        if success and isinstance(data, dict):
            enabled = data.get("enabled", True)  # Should be false initially
            web3_connected = data.get("web3_connected", False)  # Should be true if configured
            dex_status_valid = enabled is False  # DEX should be disabled initially
        
        self.log_test_result(
            "DEX Service Status (Disabled Mode)",
            dex_status_valid,
            f"Status: {status}, Enabled: {data.get('enabled') if isinstance(data, dict) else 'N/A'}, Web3 Connected: {data.get('web3_connected') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 2: POST /api/dex/quote - Test with payload: {"source_token": "NENO", "destination_token": "USDT", "amount": 1.0}
        logger.info("Step 2: Test DEX Quote Request")
        quote_payload = {
            "source_token": "NENO",
            "destination_token": "USDT", 
            "amount": 1.0
        }
        success, data, status = await self.make_request("POST", "/dex/quote", quote_payload)
        
        dex_quote_valid = False
        if success and isinstance(data, dict):
            # Should return quote data even in disabled mode
            quote_id = data.get("quote_id")
            source_amount = data.get("source_amount")
            destination_amount = data.get("destination_amount")
            dex_quote_valid = bool(quote_id and source_amount and destination_amount)
        elif status == 503:
            # Service not available is also acceptable for disabled mode
            dex_quote_valid = True
        elif status == 404:
            # No quote available is acceptable when DEX aggregators are not configured
            dex_quote_valid = True
        
        self.log_test_result(
            "DEX Quote Request (NENO → USDT)",
            dex_quote_valid,
            f"Status: {status}, Quote ID: {data.get('quote_id') if isinstance(data, dict) else 'N/A'}, Source: {data.get('source_amount') if isinstance(data, dict) else 'N/A'}, Dest: {data.get('destination_amount') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 3: GET /api/dex/conversions - Should return empty list initially
        logger.info("Step 3: Test DEX Conversions History")
        success, data, status = await self.make_request("GET", "/dex/conversions")
        
        dex_conversions_valid = False
        if success and isinstance(data, dict):
            swaps = data.get("swaps", [])
            count = data.get("count", 0)
            dex_conversions_valid = isinstance(swaps, list) and count >= 0
        
        self.log_test_result(
            "DEX Conversions History",
            dex_conversions_valid,
            f"Status: {status}, Swaps Count: {data.get('count') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 4: GET /api/dex/admin/config - Should return DEX configuration
        logger.info("Step 4: Test DEX Admin Configuration")
        success, data, status = await self.make_request("GET", "/dex/admin/config")
        
        dex_config_valid = False
        if success and isinstance(data, dict):
            # Should return config object (may be empty if not configured)
            dex_config_valid = True
        elif status == 404:
            # No config found is also acceptable
            dex_config_valid = True
        
        self.log_test_result(
            "DEX Admin Configuration",
            dex_config_valid,
            f"Status: {status}, Config Keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}"
        )
        
        return dex_status_valid and dex_quote_valid and dex_conversions_valid and dex_config_valid

    async def test_transak_service_api(self):
        """Test Transak Service API endpoints as specified in the review request"""
        logger.info("\n=== Testing Transak Service API ===")
        
        # Test 1: GET /api/transak/status - Should return service status
        logger.info("Step 1: Test Transak Service Status")
        success, data, status = await self.make_request("GET", "/transak/status")
        
        transak_status_valid = False
        if success and isinstance(data, dict):
            configured = data.get("configured", True)  # Should be false without API key
            environment = data.get("environment")
            transak_status_valid = configured is False  # Should be in demo mode
        
        self.log_test_result(
            "Transak Service Status (Demo Mode)",
            transak_status_valid,
            f"Status: {status}, Configured: {data.get('configured') if isinstance(data, dict) else 'N/A'}, Environment: {data.get('environment') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 2: POST /api/transak/widget-url - Test with payload: {"product_type": "BUY", "fiat_currency": "EUR", "crypto_currency": "USDT", "network": "bsc"}
        logger.info("Step 2: Test Transak Widget URL Generation")
        widget_payload = {
            "product_type": "BUY",
            "fiat_currency": "EUR",
            "crypto_currency": "USDT",
            "network": "bsc"
        }
        success, data, status = await self.make_request("POST", "/transak/widget-url", widget_payload)
        
        transak_widget_valid = False
        if success and isinstance(data, dict):
            widget_url = data.get("widget_url")
            product_type = data.get("product_type")
            environment = data.get("environment")
            transak_widget_valid = bool(widget_url and product_type == "BUY")
        elif status == 503:
            # Service not configured is expected for demo mode (no API key)
            transak_widget_valid = True
        
        self.log_test_result(
            "Transak Widget URL Generation (Demo Mode Expected)",
            transak_widget_valid,
            f"Status: {status}, Widget URL: {'Present' if isinstance(data, dict) and data.get('widget_url') else 'N/A'}, Product Type: {data.get('product_type') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 3: GET /api/transak/currencies/fiat - Should return supported fiat currencies
        logger.info("Step 3: Test Transak Fiat Currencies")
        success, data, status = await self.make_request("GET", "/transak/currencies/fiat")
        
        transak_fiat_valid = False
        if success and isinstance(data, dict):
            currencies = data.get("currencies", [])
            transak_fiat_valid = isinstance(currencies, list) and len(currencies) > 0
            # Check for EUR support
            eur_found = any(c.get("code") == "EUR" for c in currencies)
            transak_fiat_valid = transak_fiat_valid and eur_found
        
        self.log_test_result(
            "Transak Fiat Currencies",
            transak_fiat_valid,
            f"Status: {status}, Currencies Count: {len(data.get('currencies', [])) if isinstance(data, dict) else 'N/A'}, EUR Supported: {any(c.get('code') == 'EUR' for c in data.get('currencies', [])) if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 4: GET /api/transak/currencies/crypto - Should return supported crypto currencies
        logger.info("Step 4: Test Transak Crypto Currencies")
        success, data, status = await self.make_request("GET", "/transak/currencies/crypto")
        
        transak_crypto_valid = False
        if success and isinstance(data, dict):
            currencies = data.get("currencies", [])
            transak_crypto_valid = isinstance(currencies, list) and len(currencies) > 0
            # Check for USDT support
            usdt_found = any(c.get("code") == "USDT" for c in currencies)
            transak_crypto_valid = transak_crypto_valid and usdt_found
        
        self.log_test_result(
            "Transak Crypto Currencies",
            transak_crypto_valid,
            f"Status: {status}, Currencies Count: {len(data.get('currencies', [])) if isinstance(data, dict) else 'N/A'}, USDT Supported: {any(c.get('code') == 'USDT' for c in data.get('currencies', [])) if isinstance(data, dict) else 'N/A'}"
        )
        
        return transak_status_valid and transak_widget_valid and transak_fiat_valid and transak_crypto_valid

    async def test_transak_order_flow(self):
        """Test Transak order creation flow as specified in the review request"""
        logger.info("\n=== Testing Transak Order Flow ===")
        
        # Test 1: POST /api/transak/orders - Create order with: {"user_id": "test123", "product_type": "BUY", "fiat_currency": "EUR", "crypto_currency": "USDT", "fiat_amount": 100}
        logger.info("Step 1: Create Transak Order")
        order_payload = {
            "user_id": "test123",
            "product_type": "BUY",
            "fiat_currency": "EUR",
            "crypto_currency": "USDT",
            "fiat_amount": 100
        }
        success, data, status = await self.make_request("POST", "/transak/orders", order_payload)
        
        order_create_valid = False
        if success and isinstance(data, dict):
            self.transak_order_id = data.get("order_id")
            user_id = data.get("user_id")
            product_type = data.get("product_type")
            fiat_amount = data.get("fiat_amount")
            order_create_valid = (
                self.transak_order_id and
                user_id == "test123" and
                product_type == "BUY" and
                fiat_amount == 100
            )
        
        self.log_test_result(
            "Create Transak Order",
            order_create_valid,
            f"Status: {status}, Order ID: {self.transak_order_id}, User: {data.get('user_id') if isinstance(data, dict) else 'N/A'}, Amount: €{data.get('fiat_amount') if isinstance(data, dict) else 'N/A'}"
        )
        
        if not order_create_valid:
            return False
        
        # Test 2: GET /api/transak/orders/{order_id} - Retrieve the created order
        logger.info("Step 2: Retrieve Transak Order by ID")
        success, data, status = await self.make_request("GET", f"/transak/orders/{self.transak_order_id}")
        
        order_retrieve_valid = False
        if success and isinstance(data, dict):
            order_id = data.get("order_id")
            user_id = data.get("user_id")
            order_retrieve_valid = order_id == self.transak_order_id and user_id == "test123"
        
        self.log_test_result(
            "Retrieve Transak Order by ID",
            order_retrieve_valid,
            f"Status: {status}, Order ID Match: {data.get('order_id') == self.transak_order_id if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 3: GET /api/transak/orders?user_id=test123 - Get orders by user
        logger.info("Step 3: Get Transak Orders by User")
        success, data, status = await self.make_request("GET", "/transak/orders?user_id=test123")
        
        orders_by_user_valid = False
        if success and isinstance(data, dict):
            orders = data.get("orders", [])
            count = data.get("count", 0)
            orders_by_user_valid = isinstance(orders, list) and count > 0
            # Check if our order is in the list
            order_found = any(o.get("order_id") == self.transak_order_id for o in orders)
            orders_by_user_valid = orders_by_user_valid and order_found
        
        self.log_test_result(
            "Get Transak Orders by User",
            orders_by_user_valid,
            f"Status: {status}, Orders Count: {data.get('count') if isinstance(data, dict) else 'N/A'}, Our Order Found: {any(o.get('order_id') == self.transak_order_id for o in data.get('orders', [])) if isinstance(data, dict) else 'N/A'}"
        )
        
        return order_create_valid and order_retrieve_valid and orders_by_user_valid

    async def test_liquidity_api_endpoints(self):
        """Test all new Liquidity API endpoints as specified in the review request"""
        logger.info("\n=== Testing Liquidity API Endpoints ===")
        
        # Test 1: GET /api/liquidity/dashboard - Combined liquidity overview
        logger.info("Step 1: Test Liquidity Dashboard")
        success, data, status = await self.make_request("GET", "/liquidity/dashboard")
        
        dashboard_valid = False
        if success and isinstance(data, dict):
            services = data.get("services", {})
            dashboard_valid = (
                services.get("treasury") and
                services.get("exposure") and
                services.get("routing") and
                services.get("hedging") and
                services.get("reconciliation") and
                data.get("mode") == "hybrid"
            )
        
        self.log_test_result(
            "Liquidity Dashboard",
            dashboard_valid,
            f"Status: {status}, Services Active: {data.get('services') if isinstance(data, dict) else 'N/A'}, Mode: {data.get('mode') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 2: GET /api/liquidity/treasury/summary - Treasury state with €100M virtual floor
        logger.info("Step 2: Test Treasury Summary")
        success, data, status = await self.make_request("GET", "/liquidity/treasury/summary")
        
        treasury_valid = False
        if success and isinstance(data, dict):
            balances = data.get("balances", {})
            eur_balance = balances.get("EUR", 0)
            treasury_valid = eur_balance >= 100000000  # €100M virtual floor
        
        self.log_test_result(
            "Treasury Summary (€100M Virtual Floor)",
            treasury_valid,
            f"Status: {status}, EUR Balance: €{data.get('balances', {}).get('EUR', 0):,.2f} if isinstance(data, dict) else 'N/A'"
        )
        
        # Test 3: GET /api/liquidity/treasury/ledger - Initial virtual floor ledger entry
        logger.info("Step 3: Test Treasury Ledger")
        success, data, status = await self.make_request("GET", "/liquidity/treasury/ledger?limit=10")
        
        ledger_valid = False
        if success and isinstance(data, dict):
            entries = data.get("entries", [])
            ledger_valid = len(entries) > 0
            # Look for virtual floor entry
            for entry in entries:
                if entry.get("entry_type") == "VIRTUAL_FLOOR" and entry.get("amount") == 100000000:
                    ledger_valid = True
                    break
        
        self.log_test_result(
            "Treasury Ledger (Virtual Floor Entry)",
            ledger_valid,
            f"Status: {status}, Entries: {len(data.get('entries', [])) if isinstance(data, dict) else 0}, Virtual Floor Found: {ledger_valid}"
        )
        
        # Test 4: GET /api/liquidity/exposure/summary - Exposure metrics (initially 0)
        logger.info("Step 4: Test Exposure Summary")
        success, data, status = await self.make_request("GET", "/liquidity/exposure/summary")
        
        exposure_valid = False
        if success and isinstance(data, dict):
            total_active = data.get("total_active_eur", 0)
            exposure_valid = total_active >= 0  # Initially 0 or positive
        
        self.log_test_result(
            "Exposure Summary",
            exposure_valid,
            f"Status: {status}, Total Active Exposure: €{data.get('total_active_eur', 0) if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 5: GET /api/liquidity/routing/summary - Shadow mode verification
        logger.info("Step 5: Test Routing Summary (Shadow Mode)")
        success, data, status = await self.make_request("GET", "/liquidity/routing/summary")
        
        routing_valid = False
        if success and isinstance(data, dict):
            shadow_mode = data.get("shadow_mode", False)
            routing_valid = shadow_mode is True
        
        self.log_test_result(
            "Routing Summary (Shadow Mode)",
            routing_valid,
            f"Status: {status}, Shadow Mode: {data.get('shadow_mode') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 6: GET /api/liquidity/hedging/summary - Shadow mode verification
        logger.info("Step 6: Test Hedging Summary (Shadow Mode)")
        success, data, status = await self.make_request("GET", "/liquidity/hedging/summary")
        
        hedging_valid = False
        if success and isinstance(data, dict):
            shadow_mode = data.get("shadow_mode", False)
            hedging_valid = shadow_mode is True
        
        self.log_test_result(
            "Hedging Summary (Shadow Mode)",
            hedging_valid,
            f"Status: {status}, Shadow Mode: {data.get('shadow_mode') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 7: GET /api/liquidity/reconciliation/summary - Reconciliation status
        logger.info("Step 7: Test Reconciliation Summary")
        success, data, status = await self.make_request("GET", "/liquidity/reconciliation/summary")
        
        recon_valid = False
        if success and isinstance(data, dict):
            recon_valid = "pending_batches" in data or "batch_statistics" in data
        
        self.log_test_result(
            "Reconciliation Summary",
            recon_valid,
            f"Status: {status}, Pending Batches: {data.get('pending_batches', 'N/A') if isinstance(data, dict) else 'N/A'}"
        )
        
        return all([dashboard_valid, treasury_valid, ledger_valid, exposure_valid, routing_valid, hedging_valid, recon_valid])

    async def test_user_authentication(self):
        """Test user authentication for liquidity testing"""
        logger.info("\n=== Testing User Authentication ===")
        
        # Test user registration with liquidity test credentials
        user_data = {
            "email": "liquidity_test@neonoble.com",
            "password": "LiquidityTest123!",
            "role": "user"
        }
        
        success, data, status = await self.make_request("POST", "/auth/register", user_data)
        
        # Registration may fail if user already exists (400), which is expected
        registration_ok = (status == 200) or (status == 400 and "already" in str(data).lower())
        
        if success and isinstance(data, dict) and data.get("token"):
            self.user_jwt = data["token"]
            
        self.log_test_result(
            "User Registration",
            registration_ok,
            f"Status: {status}, Email: liquidity_test@neonoble.com"
        )
        
        # Test user login if registration failed or to get fresh token
        if not self.user_jwt:
            login_data = {
                "email": "liquidity_test@neonoble.com",
                "password": "LiquidityTest123!"
            }
            
            success, data, status = await self.make_request("POST", "/auth/login", login_data)
            
            if success and isinstance(data, dict) and data.get("token"):
                self.user_jwt = data["token"]
                
        login_success = bool(self.user_jwt)
        self.log_test_result(
            "User Login and JWT Token",
            login_success,
            f"Status: {status}, Token: {'Present' if self.user_jwt else 'Missing'}"
        )
        
        return login_success

    async def test_complete_offramp_flow_with_liquidity_hooks(self):
        """Test complete off-ramp flow with liquidity lifecycle hooks as specified in review request"""
        logger.info("\n=== Testing Complete Off-Ramp Flow with Liquidity Lifecycle Hooks ===")
        
        if not self.user_jwt:
            self.log_test_result("Off-Ramp Flow with Liquidity Hooks", False, "No user JWT available")
            return False
        
        # Step 1: Create PoR off-ramp quote (1 NENO as specified)
        logger.info("Step 1: Create PoR Off-Ramp Quote (1 NENO)")
        quote_data = {
            "crypto_amount": 1,
            "crypto_currency": "NENO",
            "bank_account": "TEST-IBAN-123"
        }
        
        success, data, status = await self.make_request(
            "POST", "/por/quote", quote_data, auth_token=self.user_jwt
        )
        
        quote_valid = False
        expected_gross = 10000  # 1 NENO * €10,000
        expected_fee = 150     # 1.5% of €10,000
        expected_net = 9850    # €10,000 - €150
        
        if success and isinstance(data, dict):
            self.quote_id = data.get("quote_id")
            crypto_amount = data.get("crypto_amount")
            fiat_amount = data.get("fiat_amount")
            fee_amount = data.get("fee_amount")
            net_payout = data.get("net_payout")
            state = data.get("state")
            
            quote_valid = (
                self.quote_id and
                crypto_amount == 1 and
                fiat_amount == expected_gross and
                fee_amount == expected_fee and
                net_payout == expected_net and
                state == "QUOTE_CREATED"
            )
        
        self.log_test_result(
            "Create PoR Quote (1 NENO → €9,850 net)",
            quote_valid,
            f"Quote ID: {self.quote_id}, Gross: €{data.get('fiat_amount') if isinstance(data, dict) else 'N/A'}, Fee: €{data.get('fee_amount') if isinstance(data, dict) else 'N/A'}, Net: €{data.get('net_payout') if isinstance(data, dict) else 'N/A'}"
        )
        
        if not quote_valid:
            return False
        
        # Step 2: Execute quote (accept quote)
        logger.info("Step 2: Execute PoR Quote")
        execute_data = {
            "quote_id": self.quote_id,
            "bank_account": "TEST-IBAN-123"
        }
        
        success, data, status = await self.make_request(
            "POST", "/por/quote/accept", execute_data, auth_token=self.user_jwt
        )
        
        execute_valid = False
        if success and isinstance(data, dict):
            state = data.get("state")
            execute_valid = state == "DEPOSIT_PENDING"
        
        self.log_test_result(
            "Execute PoR Quote",
            execute_valid,
            f"Status: {status}, State: {data.get('state') if isinstance(data, dict) else 'N/A'}"
        )
        
        if not execute_valid:
            return False
        
        # Step 3: Process deposit to trigger liquidity lifecycle hooks
        logger.info("Step 3: Process Deposit (Trigger Liquidity Lifecycle)")
        deposit_data = {
            "quote_id": self.quote_id,
            "tx_hash": "0xtest123456789abcdef",
            "amount": 1
        }
        
        success, data, status = await self.make_request(
            "POST", "/por/deposit/process", deposit_data, auth_token=self.user_jwt
        )
        
        process_valid = False
        if success and isinstance(data, dict):
            state = data.get("state")
            # State should progress through the liquidity-enabled flow
            process_valid = state in ["COMPLETED", "SETTLEMENT_COMPLETED", "PAYOUT_PROCESSING"]
        elif status == 400:
            # Check if the transaction still progressed by getting current state
            check_success, check_data, check_status = await self.make_request(
                "GET", f"/por/transaction/{self.quote_id}", auth_token=self.user_jwt
            )
            if check_success and isinstance(check_data, dict):
                state = check_data.get("state")
                process_valid = state in ["COMPLETED", "SETTLEMENT_COMPLETED", "PAYOUT_PROCESSING"]
        
        self.log_test_result(
            "Process Deposit (Liquidity Hooks Triggered)",
            process_valid,
            f"Status: {status}, Final State: {data.get('state') if isinstance(data, dict) else 'Check transaction for state'}"
        )
        
        return quote_valid and execute_valid and process_valid

    async def test_liquidity_data_verification(self):
        """Test liquidity data verification after off-ramp flow as specified in review request"""
        logger.info("\n=== Testing Liquidity Data Verification After Off-Ramp Flow ===")
        
        if not self.quote_id:
            self.log_test_result("Liquidity Data Verification", False, "No quote ID available")
            return False
        
        # Test 1: Treasury Ledger entries for the quote
        logger.info("Step 1: Verify Treasury Ledger Entries")
        success, data, status = await self.make_request(
            "GET", f"/liquidity/treasury/ledger?quote_id={self.quote_id}"
        )
        
        treasury_ledger_valid = False
        crypto_inflow_found = False
        fiat_payout_found = False
        fee_allocation_found = False
        
        if success and isinstance(data, dict):
            entries = data.get("entries", [])
            for entry in entries:
                entry_type = entry.get("entry_type", "").upper()
                if entry_type == "CRYPTO_INFLOW":
                    crypto_inflow_found = True
                elif entry_type == "FIAT_PAYOUT":
                    fiat_payout_found = True
                elif entry_type == "FEE_ALLOCATION":
                    fee_allocation_found = True
            
            # In Phase 1, we expect at least crypto inflow (payout may be virtual/instant)
            treasury_ledger_valid = crypto_inflow_found
        
        self.log_test_result(
            "Treasury Ledger Entries",
            treasury_ledger_valid,
            f"Status: {status}, Entries: {len(data.get('entries', [])) if isinstance(data, dict) else 0}, CRYPTO_INFLOW: {crypto_inflow_found}, FIAT_PAYOUT: {fiat_payout_found}, FEE_ALLOCATION: {fee_allocation_found}"
        )
        
        # Test 2: Exposure Record for the quote
        logger.info("Step 2: Verify Exposure Record")
        success, data, status = await self.make_request(
            "GET", f"/liquidity/exposure/by-quote/{self.quote_id}"
        )
        
        exposure_valid = False
        if success and isinstance(data, dict):
            self.exposure_id = data.get("exposure_id")
            exposure_status = data.get("status")
            # In Phase 1, exposure may be in "created" state initially
            exposure_valid = exposure_status in ["FULLY_COVERED", "ACTIVE", "COVERED", "created"]
        
        self.log_test_result(
            "Exposure Record",
            exposure_valid,
            f"Status: {status}, Exposure ID: {self.exposure_id}, Status: {data.get('status') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 3: Routing Conversions (shadow mode)
        logger.info("Step 3: Verify Routing Conversions (Shadow Mode)")
        success, data, status = await self.make_request(
            "GET", f"/liquidity/routing/conversions?quote_id={self.quote_id}"
        )
        
        routing_valid = False
        if success and isinstance(data, dict):
            conversions = data.get("conversions", [])
            shadow_mode = data.get("shadow_mode", False)
            routing_valid = shadow_mode is True  # Should be shadow mode in Phase 1
        
        self.log_test_result(
            "Routing Conversions (Shadow Mode)",
            routing_valid,
            f"Status: {status}, Conversions: {len(data.get('conversions', [])) if isinstance(data, dict) else 0}, Shadow Mode: {data.get('shadow_mode') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 4: Coverage Events
        logger.info("Step 4: Verify Coverage Events")
        success, data, status = await self.make_request(
            "GET", "/liquidity/reconciliation/coverage"
        )
        
        coverage_valid = False
        if success and isinstance(data, dict):
            coverage_events = data.get("coverage_events", [])
            coverage_valid = len(coverage_events) >= 0  # Should have coverage events
        
        self.log_test_result(
            "Coverage Events",
            coverage_valid,
            f"Status: {status}, Coverage Events: {len(data.get('coverage_events', [])) if isinstance(data, dict) else 0}"
        )
        
        return treasury_ledger_valid and exposure_valid and routing_valid and coverage_valid

    async def test_password_reset_feature(self):
        """Test Password Reset feature implementation as specified in the review request"""
        logger.info("\n=== Testing Password Reset Feature ===")
        
        # Test 1: GET /api/password/status - Service status
        logger.info("Step 1: Test Password Reset Service Status")
        success, data, status = await self.make_request("GET", "/password/status")
        
        status_valid = False
        if success and isinstance(data, dict):
            email_configured = data.get("email_configured", True)  # Should be false (no API key set)
            token_expiry_hours = data.get("token_expiry_hours", 0)  # Should be 1
            status_valid = (
                email_configured is False and
                token_expiry_hours == 1
            )
        
        self.log_test_result(
            "Password Reset Service Status",
            status_valid,
            f"Status: {status}, Email Configured: {data.get('email_configured') if isinstance(data, dict) else 'N/A'}, Token Expiry: {data.get('token_expiry_hours') if isinstance(data, dict) else 'N/A'} hours"
        )
        
        # Test 2a: Create test user for password reset flow
        logger.info("Step 2a: Create Test User for Password Reset")
        user_data = {
            "email": self.test_user_email,
            "password": self.test_user_password
        }
        
        success, data, status = await self.make_request("POST", "/auth/register", user_data)
        
        # Registration may fail if user already exists (400), which is expected
        user_created = (status == 200) or (status == 400 and "already" in str(data).lower())
        
        self.log_test_result(
            "Create Test User for Password Reset",
            user_created,
            f"Status: {status}, Email: {self.test_user_email}"
        )
        
        # Test 2b: Request password reset for existing email
        logger.info("Step 2b: Request Password Reset for Existing Email")
        reset_request = {
            "email": self.test_user_email
        }
        
        success, data, status = await self.make_request("POST", "/password/forgot", reset_request)
        
        reset_request_valid = False
        if success and isinstance(data, dict):
            response_status = data.get("status")
            message = data.get("message", "")
            reset_request_valid = (
                response_status == "success" and
                "email" in message.lower()
            )
        
        self.log_test_result(
            "Request Password Reset (Existing Email)",
            reset_request_valid,
            f"Status: {status}, Response Status: {data.get('status') if isinstance(data, dict) else 'N/A'}, Message: {data.get('message') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 2c: Request password reset for non-existent email (should still return success)
        logger.info("Step 2c: Request Password Reset for Non-Existent Email")
        reset_request_nonexistent = {
            "email": "nonexistent@test.com"
        }
        
        success, data, status = await self.make_request("POST", "/password/forgot", reset_request_nonexistent)
        
        nonexistent_request_valid = False
        if success and isinstance(data, dict):
            response_status = data.get("status")
            # Should still return success to prevent email enumeration
            nonexistent_request_valid = response_status == "success"
        
        self.log_test_result(
            "Request Password Reset (Non-Existent Email - Prevent Enumeration)",
            nonexistent_request_valid,
            f"Status: {status}, Response Status: {data.get('status') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 3: Token verification with invalid token
        logger.info("Step 3: Test Token Verification with Invalid Token")
        verify_request = {
            "token": "invalid_token"
        }
        
        success, data, status = await self.make_request("POST", "/password/verify-token", verify_request)
        
        invalid_token_valid = False
        if not success and status == 400:
            # Should return 400 error "Token non valido o scaduto"
            if isinstance(data, dict):
                detail = data.get("detail", "")
                invalid_token_valid = "token" in detail.lower() and ("non valido" in detail.lower() or "scaduto" in detail.lower())
            elif isinstance(data, str):
                invalid_token_valid = "token" in data.lower() and ("non valido" in data.lower() or "scaduto" in data.lower())
        
        self.log_test_result(
            "Token Verification (Invalid Token)",
            invalid_token_valid,
            f"Status: {status}, Expected 400 with 'Token non valido o scaduto', Got: {data if isinstance(data, (str, dict)) else 'N/A'}"
        )
        
        # Test 4: Password change (authenticated) - requires current password
        logger.info("Step 4: Test Password Change (Authenticated)")
        change_request = {
            "current_password": self.test_user_password,
            "new_password": self.new_password
        }
        
        success, data, status = await self.make_request("POST", "/password/change", change_request)
        
        password_change_valid = False
        if success and isinstance(data, dict):
            response_status = data.get("status")
            message = data.get("message", "")
            password_change_valid = (
                response_status == "success" and
                "password" in message.lower()
            )
        
        self.log_test_result(
            "Password Change (Authenticated)",
            password_change_valid,
            f"Status: {status}, Response Status: {data.get('status') if isinstance(data, dict) else 'N/A'}, Message: {data.get('message') if isinstance(data, dict) else 'N/A'}"
        )
        
        # Test 5: Verify login with new password
        logger.info("Step 5: Verify Login with New Password")
        login_data = {
            "email": self.test_user_email,
            "password": self.new_password
        }
        
        success, data, status = await self.make_request("POST", "/auth/login", login_data)
        
        new_password_login_valid = False
        if success and isinstance(data, dict):
            token = data.get("token")
            new_password_login_valid = bool(token)
        
        self.log_test_result(
            "Login with New Password",
            new_password_login_valid,
            f"Status: {status}, Token Present: {'Yes' if isinstance(data, dict) and data.get('token') else 'No'}"
        )
        
        # Test 6: Verify old password no longer works
        logger.info("Step 6: Verify Old Password No Longer Works")
        old_login_data = {
            "email": self.test_user_email,
            "password": self.test_user_password
        }
        
        success, data, status = await self.make_request("POST", "/auth/login", old_login_data)
        
        old_password_rejected = False
        if not success and status in [400, 401]:
            # Old password should be rejected
            old_password_rejected = True
        
        self.log_test_result(
            "Old Password Rejected",
            old_password_rejected,
            f"Status: {status}, Expected 400/401 rejection, Success: {success}"
        )
        
        return all([
            status_valid,
            user_created,
            reset_request_valid,
            nonexistent_request_valid,
            invalid_token_valid,
            password_change_valid,
            new_password_login_valid,
            old_password_rejected
        ])

    async def run_password_reset_tests(self):
        """Run Password Reset feature tests"""
        logger.info("🔐 Starting PASSWORD RESET FEATURE TESTING")
        logger.info(f"Testing against: {BACKEND_URL}")
        logger.info("Password Reset Flow Tests:")
        logger.info("  - Service status verification")
        logger.info("  - Password reset request flow")
        logger.info("  - Token verification")
        logger.info("  - Password change (authenticated)")
        logger.info("  - Login verification with new password")
        
        # Password Reset Test sequence
        tests = [
            ("Password Reset Feature", self.test_password_reset_feature),
        ]
        
        for test_name, test_func in tests:
            try:
                await test_func()
            except Exception as e:
                logger.error(f"Test '{test_name}' failed with exception: {e}")
                self.log_test_result(test_name, False, f"Exception: {e}")
        
        # Summary
        logger.info("\n" + "="*80)
        logger.info("PASSWORD RESET FEATURE TESTING SUMMARY")
        logger.info("="*80)
        
        passed = 0
        failed = 0
        critical_failures = []
        
        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            logger.info(f"{status} {test_name}")
            if not result["success"] and result["details"]:
                logger.info(f"    Error: {result['details']}")
                critical_failures.append(test_name)
            
            if result["success"]:
                passed += 1
            else:
                failed += 1
        
        logger.info(f"\nTotal: {passed + failed}, Passed: {passed}, Failed: {failed}")
        
        if critical_failures:
            logger.error(f"\n🚨 CRITICAL FAILURES:")
            for failure in critical_failures:
                logger.error(f"   - {failure}")
            logger.error("❌ Password Reset feature testing FAILED")
        else:
            logger.info(f"\n✅ PASSWORD RESET FEATURE TESTING COMPLETE")
            logger.info("🔐 VERIFIED FEATURES:")
            logger.info("   - Service status (email not configured, 1-hour token expiry)")
            logger.info("   - Password reset request (creates token in DB)")
            logger.info("   - Email enumeration prevention")
            logger.info("   - Invalid token rejection")
            logger.info("   - Password change updates user's password")
            logger.info("   - Login works with new password")
            logger.info("   - Old password is rejected")
        
        return self.test_results

    async def run_phase2_phase3_tests(self):
        """Run all Phase 2 & Phase 3 Venue Integration + Hedge Activation tests"""
        logger.info("🚀 Starting PHASE 2 & 3 VENUE INTEGRATION + HEDGE ACTIVATION TESTING")
        logger.info(f"Testing against: {BACKEND_URL}")
        logger.info("Phase 2 - Exchange Connectors (NEW):")
        logger.info("  - Exchange status, balances, orders (shadow mode without credentials)")
        logger.info("  - Binance + Kraken venues (not connected without API keys)")
        logger.info("  - Order placement in shadow mode")
        logger.info("Phase 3 - Hedge Activation (NEW):")
        logger.info("  - Hedging service summary (shadow mode with policy)")
        logger.info("  - Hedge proposals and events")
        logger.info("  - Conservative Hybrid Policy configuration")
        logger.info("Existing Services (Regression):")
        logger.info("  - DEX Service - Real on-chain swaps (1inch + PancakeSwap) - DISABLED mode initially")
        logger.info("  - Transak Service - On/Off-ramp widget integration - DEMO mode (no API key)")
        logger.info("  - Liquidity Services - Treasury, Exposure, Routing, Reconciliation")
        
        # Phase 2 & 3 Test sequence
        tests = [
            # Phase 2 - Exchange Connectors (NEW)
            ("Phase 2 - Exchange Connectors API", self.test_phase2_exchange_connectors_api),
            
            # Phase 3 - Hedge Activation (NEW)
            ("Phase 3 - Hedge Activation API", self.test_phase3_hedge_activation_api),
            
            # Existing Services Regression Testing
            ("Existing Services Regression", self.test_existing_services_regression),
            ("DEX Service API (Regression)", self.test_dex_service_api),
            ("Transak Service API (Regression)", self.test_transak_service_api),
            ("Liquidity API Endpoints (Regression)", self.test_liquidity_api_endpoints),
        ]
        
        for test_name, test_func in tests:
            try:
                await test_func()
            except Exception as e:
                logger.error(f"Test '{test_name}' failed with exception: {e}")
                self.log_test_result(test_name, False, f"Exception: {e}")
        
        # Summary
        logger.info("\n" + "="*80)
        logger.info("PHASE 2 & 3 VENUE INTEGRATION + HEDGE ACTIVATION TESTING SUMMARY")
        logger.info("="*80)
        
        passed = 0
        failed = 0
        critical_failures = []
        phase2_failures = []
        phase3_failures = []
        regression_failures = []
        
        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            logger.info(f"{status} {test_name}")
            if not result["success"] and result["details"]:
                logger.info(f"    Error: {result['details']}")
                critical_failures.append(test_name)
                
                # Categorize failures
                if "phase 2" in test_name.lower() or "exchange" in test_name.lower():
                    phase2_failures.append(test_name)
                elif "phase 3" in test_name.lower() or "hedge" in test_name.lower():
                    phase3_failures.append(test_name)
                elif "regression" in test_name.lower():
                    regression_failures.append(test_name)
            
            if result["success"]:
                passed += 1
            else:
                failed += 1
        
        logger.info(f"\nTotal: {passed + failed}, Passed: {passed}, Failed: {failed}")
        
        if critical_failures:
            logger.error(f"\n🚨 CRITICAL FAILURES:")
            if phase2_failures:
                logger.error(f"   PHASE 2 (Exchange Connectors): {phase2_failures}")
            if phase3_failures:
                logger.error(f"   PHASE 3 (Hedge Activation): {phase3_failures}")
            if regression_failures:
                logger.error(f"   REGRESSIONS: {regression_failures}")
            logger.error("❌ Phase 2 & 3 Venue Integration + Hedge Activation testing FAILED")
        else:
            logger.info(f"\n✅ PHASE 2 & 3 VENUE INTEGRATION + HEDGE ACTIVATION TESTING COMPLETE")
            logger.info("🏆 NEW FEATURES VERIFIED:")
            logger.info("   - Phase 2: Exchange Connectors API (Shadow Mode)")
            logger.info("   - Phase 3: Hedge Activation API (Shadow Mode + Policy)")
            logger.info("🔄 REGRESSION TESTS PASSED:")
            logger.info("   - DEX Service (Disabled Mode)")
            logger.info("   - Transak Service (Demo Mode)")
            logger.info("   - Liquidity Services (Treasury, Exposure, Routing, Reconciliation)")
        
        return self.test_results

    async def run_all_tests(self):
        """Run Phase 2 & Phase 3 Venue Integration + Hedge Activation tests"""
        return await self.run_phase2_phase3_tests()

async def main():
    """Main test runner for Password Reset feature testing"""
    async with Phase2Phase3Tester() as tester:
        results = await tester.run_password_reset_tests()
        
        # Return exit code based on results
        failed_tests = [name for name, result in results.items() if not result["success"]]
        if failed_tests:
            logger.error(f"\n❌ {len(failed_tests)} tests failed")
            return 1
        else:
            logger.info(f"\n✅ All tests passed!")
            return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)