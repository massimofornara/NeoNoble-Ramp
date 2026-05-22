"""
Exchange Utilities — Shared helpers for the NENO exchange.
Extracted from neno_exchange_routes.py for modularization.
"""

from database.mongodb import get_database

# ── Market reference prices (EUR) ──
MARKET_PRICES_EUR = {
    "BTC": 60787.0,
    "ETH": 1769.0,
    "BNB": 555.36,
    "USDT": 0.92,
    "USDC": 0.92,
    "MATIC": 0.55,
    "SOL": 74.72,
    "XRP": 1.21,
    "ADA": 0.38,
    "DOGE": 0.082,
    "EUR": 1.0,
    "USD": 0.92,
}

NENO_BASE_PRICE = 10_000.0
PLATFORM_FEE = 0.003
SUPPORTED_ASSETS = list(MARKET_PRICES_EUR.keys())
