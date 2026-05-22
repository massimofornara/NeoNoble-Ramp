"""
NENO Price History Service - Generates and stores historical price data.

Provides:
- OHLCV candlestick data for NENO
- Multiple timeframes (1m, 5m, 15m, 1h, 4h, 1d)
- Simulated price movements with realistic patterns
"""

import os
import logging
import random
from typing import List, Dict, Optional
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field, asdict
from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# Base NENO price
NENO_BASE_PRICE = float(os.environ.get('NENO_PRICE_EUR', '10000.0'))

# Timeframe configurations (in seconds)
TIMEFRAMES = {
    '1m': 60,
    '5m': 300,
    '15m': 900,
    '1h': 3600,
    '4h': 14400,
    '1d': 86400
}


@dataclass
class Candle:
    """OHLCV candlestick data."""
    timestamp: int  # Unix timestamp in milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class PriceAlert:
    """Price alert configuration."""
    alert_id: str
    user_id: str
    symbol: str
    condition: str  # 'above' or 'below'
    target_price: float
    triggered: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    triggered_at: Optional[str] = None


class NenoPriceHistoryService:
    """
    Service for generating and managing NENO price history.
    
    Features:
    - Generate realistic OHLCV candlestick data
    - Store and retrieve historical data
    - Support multiple timeframes
    - Price alerts management
    """
    
    def __init__(self, db: Optional[AsyncIOMotorDatabase] = None):
        self.db = db
        self._price_cache: Dict[str, List[Candle]] = {}
        self._current_price = NENO_BASE_PRICE
        self._last_update = datetime.now(timezone.utc)
        
        # Initialize with historical data
        self._generate_historical_data()
        
        logger.info(f"[NENO-HISTORY] Price history service initialized. Base price: €{NENO_BASE_PRICE:,.2f}")
    
    def _generate_historical_data(self):
        """Generate initial historical data for all timeframes."""
        now = datetime.now(timezone.utc)
        
        for timeframe, seconds in TIMEFRAMES.items():
            candles = []
            
            # Generate candles going back in time
            if timeframe == '1m':
                num_candles = 1440  # 24 hours
            elif timeframe == '5m':
                num_candles = 576  # 48 hours
            elif timeframe == '15m':
                num_candles = 384  # 4 days
            elif timeframe == '1h':
                num_candles = 168  # 7 days
            elif timeframe == '4h':
                num_candles = 180  # 30 days
            else:  # 1d
                num_candles = 365  # 1 year
            
            price = NENO_BASE_PRICE
            
            for i in range(num_candles, 0, -1):
                timestamp = now - timedelta(seconds=seconds * i)
                candle = self._generate_candle(timestamp, price, timeframe)
                candles.append(candle)
                price = candle.close
            
            self._price_cache[timeframe] = candles
            self._current_price = price
    
    def _generate_candle(self, timestamp: datetime, open_price: float, timeframe: str) -> Candle:
        """Generate a single candle with realistic price movement."""
        # Volatility based on timeframe
        volatility_map = {
            '1m': 0.0005,
            '5m': 0.001,
            '15m': 0.0015,
            '1h': 0.002,
            '4h': 0.003,
            '1d': 0.005
        }
        
        volatility = volatility_map.get(timeframe, 0.001)
        
        # Random price movement with slight upward bias
        change = random.gauss(0.00001, volatility)
        
        # Generate OHLC
        close_price = open_price * (1 + change)
        
        # Ensure price stays within reasonable bounds (±2% from base)
        min_price = NENO_BASE_PRICE * 0.98
        max_price = NENO_BASE_PRICE * 1.02
        close_price = max(min_price, min(max_price, close_price))
        
        # High and low
        high_price = max(open_price, close_price) * (1 + abs(random.gauss(0, volatility / 2)))
        low_price = min(open_price, close_price) * (1 - abs(random.gauss(0, volatility / 2)))
        
        # Volume (random with time-of-day pattern)
        hour = timestamp.hour
        base_volume = 100
        if 8 <= hour <= 18:  # Higher volume during business hours
            base_volume = 200
        volume = base_volume * (1 + random.random())
        
        return Candle(
            timestamp=int(timestamp.timestamp() * 1000),
            open=round(open_price, 2),
            high=round(high_price, 2),
            low=round(low_price, 2),
            close=round(close_price, 2),
            volume=round(volume, 2)
        )
    
    def get_candles(
        self,
        timeframe: str = '1h',
        limit: int = 100,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> List[Dict]:
        """
        Get historical candles for NENO.
        
        Args:
            timeframe: Candle timeframe (1m, 5m, 15m, 1h, 4h, 1d)
            limit: Maximum number of candles to return
            start_time: Start timestamp in milliseconds
            end_time: End timestamp in milliseconds
        
        Returns:
            List of candle dictionaries
        """
        if timeframe not in self._price_cache:
            return []
        
        candles = self._price_cache[timeframe]
        
        # Filter by time range if specified
        if start_time:
            candles = [c for c in candles if c.timestamp >= start_time]
        if end_time:
            candles = [c for c in candles if c.timestamp <= end_time]
        
        # Return limited results
        return [c.to_dict() for c in candles[-limit:]]
    
    def get_current_price(self) -> Dict:
        """Get current NENO price with 24h stats."""
        candles_24h = self._price_cache.get('1h', [])[-24:]
        
        if not candles_24h:
            return {
                'price': NENO_BASE_PRICE,
                'change_24h': 0,
                'change_pct_24h': 0,
                'high_24h': NENO_BASE_PRICE,
                'low_24h': NENO_BASE_PRICE,
                'volume_24h': 0
            }
        
        current = candles_24h[-1].close if candles_24h else NENO_BASE_PRICE
        open_24h = candles_24h[0].open if candles_24h else NENO_BASE_PRICE
        
        high_24h = max(c.high for c in candles_24h)
        low_24h = min(c.low for c in candles_24h)
        volume_24h = sum(c.volume for c in candles_24h)
        
        change = current - open_24h
        change_pct = (change / open_24h) * 100 if open_24h > 0 else 0
        
        return {
            'price': round(current, 2),
            'change_24h': round(change, 2),
            'change_pct_24h': round(change_pct, 4),
            'high_24h': round(high_24h, 2),
            'low_24h': round(low_24h, 2),
            'volume_24h': round(volume_24h, 2)
        }
    
    def update_price(self):
        """
        Update current price with a new tick.
        Called periodically to add new candles.
        """
        now = datetime.now(timezone.utc)
        
        for timeframe, seconds in TIMEFRAMES.items():
            candles = self._price_cache.get(timeframe, [])
            
            if candles:
                last_candle = candles[-1]
                last_time = datetime.fromtimestamp(last_candle.timestamp / 1000, tz=timezone.utc)
                
                # Check if we need a new candle
                if (now - last_time).total_seconds() >= seconds:
                    new_candle = self._generate_candle(now, last_candle.close, timeframe)
                    candles.append(new_candle)
                    
                    # Keep cache size manageable
                    max_candles = {
                        '1m': 2880,
                        '5m': 1152,
                        '15m': 768,
                        '1h': 336,
                        '4h': 360,
                        '1d': 730
                    }
                    if len(candles) > max_candles.get(timeframe, 500):
                        candles.pop(0)
                    
                    self._price_cache[timeframe] = candles
                    self._current_price = new_candle.close
        
        self._last_update = now
    
    def get_price_statistics(self) -> Dict:
        """Get comprehensive price statistics."""
        stats = {
            'current': self.get_current_price(),
            'all_time_high': NENO_BASE_PRICE * 1.02,
            'all_time_low': NENO_BASE_PRICE * 0.98,
            'market_cap': NENO_BASE_PRICE * 999885554,  # Total supply
            'circulating_supply': 999885554,
            'last_updated': self._last_update.isoformat()
        }
        return stats


# Global instance
_price_history_service: Optional[NenoPriceHistoryService] = None


def get_price_history_service(db: Optional[AsyncIOMotorDatabase] = None) -> NenoPriceHistoryService:
    """Get or create the price history service instance."""
    global _price_history_service
    if _price_history_service is None:
        _price_history_service = NenoPriceHistoryService(db)
    return _price_history_service


def set_price_history_service(service: NenoPriceHistoryService):
    """Set the price history service instance."""
    global _price_history_service
    _price_history_service = service
