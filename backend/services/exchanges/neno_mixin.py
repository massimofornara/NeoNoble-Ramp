"""
NENO Integration Mixin - Adds $NENO support to all exchange connectors.

This mixin intercepts NENO-related calls and routes them to the
virtual NENO exchange, making NENO appear as a native listing
on all exchanges.
"""

import logging
from typing import Optional, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# NENO Configuration
NENO_PRICE_EUR = 10000.0
NENO_PRICE_USD = NENO_PRICE_EUR * 1.08


def is_neno_symbol(symbol: str) -> bool:
    """Check if symbol contains NENO."""
    return 'NENO' in symbol.upper()


def get_neno_ticker_data(symbol: str) -> dict:
    """Get NENO ticker data for any symbol format."""
    # Determine quote currency and price
    symbol_upper = symbol.upper().replace('-', '')
    
    if 'EUR' in symbol_upper:
        price = NENO_PRICE_EUR
    elif 'USD' in symbol_upper or 'USDT' in symbol_upper:
        price = NENO_PRICE_USD
    else:
        price = NENO_PRICE_EUR
    
    # Add small spread (0.1%)
    spread = price * 0.001
    
    # Vary volume slightly based on time
    base_volume = 1250.0
    volume_variance = (datetime.now().minute % 10) * 50
    
    return {
        'symbol': symbol,
        'bid': price - spread / 2,
        'ask': price + spread / 2,
        'last': price,
        'volume_24h': base_volume + volume_variance,
        'high_24h': price * 1.002,
        'low_24h': price * 0.998,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }


def get_neno_balance_data() -> dict:
    """Get NENO balance data."""
    return {
        'currency': 'NENO',
        'total': 100.0,  # Platform holds NENO for distribution
        'available': 100.0,
        'locked': 0.0
    }


class NenoIntegrationMixin:
    """
    Mixin class that adds NENO support to exchange connectors.
    
    When a connector inherits this mixin, all NENO-related calls
    are automatically handled with simulated data that matches
    the platform's fixed NENO price.
    """
    
    def _check_neno_ticker(self, symbol: str):
        """
        Check if this is a NENO ticker request and return data if so.
        Returns None if not a NENO symbol.
        """
        if is_neno_symbol(symbol):
            return get_neno_ticker_data(symbol)
        return None
    
    def _check_neno_balance(self, currency: str):
        """
        Check if this is a NENO balance request and return data if so.
        Returns None if not NENO.
        """
        if currency.upper() == 'NENO':
            return get_neno_balance_data()
        return None
    
    def _is_neno_order(self, symbol: str) -> bool:
        """Check if this is a NENO order."""
        return is_neno_symbol(symbol)
