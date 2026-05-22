import httpx
import logging
import asyncio
import os
from typing import Dict, Optional
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

# CoinGecko API configuration
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"

# Fixed NENO price in EUR
NENO_PRICE_EUR = 10000.0

# Cache configuration - longer TTL to reduce API calls
CACHE_TTL_SECONDS = int(os.environ.get('PRICE_CACHE_TTL', 300))  # 5 minutes default
CACHE_STALE_TTL_SECONDS = int(os.environ.get('PRICE_CACHE_STALE_TTL', 3600))  # 1 hour stale fallback

# Rate limit handling
MIN_REQUEST_INTERVAL = 10  # Minimum seconds between CoinGecko requests
_last_request_time: Optional[datetime] = None
_rate_limit_backoff = 0  # Exponential backoff multiplier

# Price cache with timestamps
_price_cache: Dict[str, tuple[float, datetime]] = {}

# Mapping of our crypto codes to CoinGecko IDs
CRYPTO_TO_COINGECKO = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "USDT": "tether",
    "USDC": "usd-coin",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "MATIC": "matic-network",
    "DOT": "polkadot",
    "AVAX": "avalanche-2",
    "LINK": "chainlink",
    "UNI": "uniswap",
}

# Supported cryptocurrencies
SUPPORTED_CRYPTOS = list(CRYPTO_TO_COINGECKO.keys()) + ["NENO"]

# Fee configuration
FEE_PERCENTAGE = 1.5  # 1.5% fee


class PricingService:
    """
    Pricing service with intelligent caching and rate-limit handling.
    
    Features:
    - 5-minute cache TTL (configurable via PRICE_CACHE_TTL env var)
    - 1-hour stale fallback when API unavailable
    - Exponential backoff on rate limits
    - Background cache warming
    """
    
    def __init__(self):
        self._http_client: Optional[httpx.AsyncClient] = None
        self._cache_refresh_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
    
    async def get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=15.0,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "NeoNoble-Ramp/2.0"
                }
            )
        return self._http_client
    
    async def close(self):
        if self._cache_refresh_task:
            self._cache_refresh_task.cancel()
            try:
                await self._cache_refresh_task
            except asyncio.CancelledError:
                pass
        
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
    
    async def start_cache_refresh(self):
        """Start background cache refresh task."""
        if self._cache_refresh_task is None or self._cache_refresh_task.done():
            self._cache_refresh_task = asyncio.create_task(self._background_refresh())
            logger.info("Started price cache background refresh")
    
    async def _background_refresh(self):
        """Background task to keep cache warm."""
        while True:
            try:
                # Refresh every CACHE_TTL_SECONDS - 30 seconds (before expiry)
                await asyncio.sleep(max(CACHE_TTL_SECONDS - 30, 60))
                
                # Refresh all prices
                await self._fetch_all_prices_from_api()
                logger.debug("Background cache refresh completed")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Background cache refresh failed: {e}")
                await asyncio.sleep(60)  # Wait before retrying
    
    def _get_cached_price(self, crypto: str, allow_stale: bool = False) -> Optional[float]:
        """
        Get price from cache.
        
        Args:
            crypto: Cryptocurrency code
            allow_stale: If True, return expired cache up to CACHE_STALE_TTL_SECONDS
        """
        if crypto in _price_cache:
            price, cached_at = _price_cache[crypto]
            age = (datetime.now(timezone.utc) - cached_at).total_seconds()
            
            # Fresh cache
            if age < CACHE_TTL_SECONDS:
                return price
            
            # Stale but usable
            if allow_stale and age < CACHE_STALE_TTL_SECONDS:
                logger.debug(f"Using stale cache for {crypto} (age: {age:.0f}s)")
                return price
        
        return None
    
    def _cache_price(self, crypto: str, price: float):
        """Cache a price with timestamp."""
        _price_cache[crypto] = (price, datetime.now(timezone.utc))
    
    def _cache_all_prices(self, prices: Dict[str, float]):
        """Cache multiple prices at once."""
        now = datetime.now(timezone.utc)
        for crypto, price in prices.items():
            _price_cache[crypto] = (price, now)
    
    async def _wait_for_rate_limit(self):
        """Wait if we're making requests too fast."""
        global _last_request_time, _rate_limit_backoff
        
        if _last_request_time is None:
            _last_request_time = datetime.now(timezone.utc)
            return
        
        elapsed = (datetime.now(timezone.utc) - _last_request_time).total_seconds()
        wait_time = MIN_REQUEST_INTERVAL * (2 ** _rate_limit_backoff)
        
        if elapsed < wait_time:
            sleep_time = wait_time - elapsed
            logger.debug(f"Rate limit wait: {sleep_time:.1f}s (backoff: {_rate_limit_backoff})")
            await asyncio.sleep(sleep_time)
        
        _last_request_time = datetime.now(timezone.utc)
    
    async def _fetch_all_prices_from_api(self) -> Dict[str, float]:
        """Fetch all prices from CoinGecko API with rate limit handling."""
        global _rate_limit_backoff
        
        async with self._lock:
            await self._wait_for_rate_limit()
            
            try:
                coingecko_ids = ",".join(CRYPTO_TO_COINGECKO.values())
                client = await self.get_http_client()
                
                response = await client.get(
                    f"{COINGECKO_API_URL}/simple/price",
                    params={
                        "ids": coingecko_ids,
                        "vs_currencies": "eur"
                    }
                )
                
                if response.status_code == 429:
                    # Rate limited - increase backoff
                    _rate_limit_backoff = min(_rate_limit_backoff + 1, 5)
                    logger.warning(f"CoinGecko rate limit hit, backoff: {_rate_limit_backoff}")
                    raise httpx.HTTPStatusError(
                        "Rate limited", 
                        request=response.request, 
                        response=response
                    )
                
                response.raise_for_status()
                
                # Success - reset backoff
                _rate_limit_backoff = max(_rate_limit_backoff - 1, 0)
                
                data = response.json()
                prices = {}
                
                for crypto, coingecko_id in CRYPTO_TO_COINGECKO.items():
                    if coingecko_id in data and "eur" in data[coingecko_id]:
                        prices[crypto] = data[coingecko_id]["eur"]
                
                # Cache all prices
                self._cache_all_prices(prices)
                logger.info(f"Fetched {len(prices)} prices from CoinGecko (cache TTL: {CACHE_TTL_SECONDS}s)")
                
                return prices
                
            except httpx.HTTPError as e:
                logger.error(f"CoinGecko API error: {e}")
                raise
    
    async def get_price_eur(self, crypto: str) -> float:
        """
        Get the price of a cryptocurrency in EUR.
        
        Uses cache first, then API, with stale fallback.
        """
        crypto = crypto.upper()
        
        # NENO has a fixed price
        if crypto == "NENO":
            return NENO_PRICE_EUR
        
        # Check if supported
        if crypto not in CRYPTO_TO_COINGECKO:
            raise ValueError(f"Unsupported cryptocurrency: {crypto}. Supported: {SUPPORTED_CRYPTOS}")
        
        # Check fresh cache
        cached_price = self._get_cached_price(crypto)
        if cached_price is not None:
            return cached_price
        
        # Try to fetch from API
        try:
            prices = await self._fetch_all_prices_from_api()
            if crypto in prices:
                return prices[crypto]
        except Exception as e:
            logger.warning(f"API fetch failed: {e}")
        
        # Fall back to stale cache
        stale_price = self._get_cached_price(crypto, allow_stale=True)
        if stale_price is not None:
            logger.warning(f"Using stale price for {crypto}: {stale_price} EUR")
            return stale_price
        
        raise ValueError(f"Unable to fetch price for {crypto}")
    
    async def get_all_prices_eur(self) -> Dict[str, float]:
        """Get prices for all supported cryptocurrencies."""
        prices = {"NENO": NENO_PRICE_EUR}
        
        # Check if we have fresh cache for most cryptos (allow some missing)
        cached_count = 0
        for crypto in CRYPTO_TO_COINGECKO.keys():
            cached = self._get_cached_price(crypto)
            if cached is not None:
                prices[crypto] = cached
                cached_count += 1
        
        # If we have >80% cached, don't fetch from API
        cache_threshold = len(CRYPTO_TO_COINGECKO) * 0.8
        if cached_count >= cache_threshold:
            # Also try stale cache for any missing
            for crypto in CRYPTO_TO_COINGECKO.keys():
                if crypto not in prices:
                    stale = self._get_cached_price(crypto, allow_stale=True)
                    if stale is not None:
                        prices[crypto] = stale
            return prices
        
        # Fetch from API
        try:
            api_prices = await self._fetch_all_prices_from_api()
            prices.update(api_prices)
        except Exception as e:
            logger.warning(f"API fetch failed, using stale cache: {e}")
            # Use stale cache as fallback
            for crypto in CRYPTO_TO_COINGECKO.keys():
                if crypto not in prices:
                    stale = self._get_cached_price(crypto, allow_stale=True)
                    if stale is not None:
                        prices[crypto] = stale
        
        return prices
    
    def get_cache_status(self) -> Dict:
        """Get cache status for monitoring."""
        now = datetime.now(timezone.utc)
        status = {
            "cache_ttl_seconds": CACHE_TTL_SECONDS,
            "stale_ttl_seconds": CACHE_STALE_TTL_SECONDS,
            "rate_limit_backoff": _rate_limit_backoff,
            "cached_prices": {}
        }
        
        for crypto, (price, cached_at) in _price_cache.items():
            age = (now - cached_at).total_seconds()
            status["cached_prices"][crypto] = {
                "price": price,
                "age_seconds": round(age, 1),
                "fresh": age < CACHE_TTL_SECONDS,
                "stale": CACHE_TTL_SECONDS <= age < CACHE_STALE_TTL_SECONDS,
                "expired": age >= CACHE_STALE_TTL_SECONDS
            }
        
        return status
    
    def calculate_fee(self, fiat_amount: float) -> float:
        """Calculate fee for a transaction."""
        return round(fiat_amount * (FEE_PERCENTAGE / 100), 2)
    
    async def calculate_onramp_quote(
        self,
        fiat_amount: float,
        crypto: str,
        fiat_currency: str = "EUR"
    ) -> dict:
        """Calculate onramp quote (Fiat -> Crypto)."""
        price = await self.get_price_eur(crypto)
        fee = self.calculate_fee(fiat_amount)
        crypto_amount = fiat_amount / price
        
        return {
            "fiat_amount": fiat_amount,
            "fiat_currency": fiat_currency,
            "crypto_amount": round(crypto_amount, 8),
            "crypto_currency": crypto,
            "exchange_rate": price,
            "fee_amount": fee,
            "fee_currency": fiat_currency,
            "fee_percentage": FEE_PERCENTAGE,
            "total_fiat": round(fiat_amount + fee, 2),
            "price_source": "fixed" if crypto == "NENO" else "coingecko"
        }
    
    async def calculate_offramp_quote(
        self,
        crypto_amount: float,
        crypto: str,
        fiat_currency: str = "EUR"
    ) -> dict:
        """Calculate offramp quote (Crypto -> Fiat)."""
        price = await self.get_price_eur(crypto)
        fiat_amount = crypto_amount * price
        fee = self.calculate_fee(fiat_amount)
        
        return {
            "fiat_amount": round(fiat_amount, 2),
            "fiat_currency": fiat_currency,
            "crypto_amount": crypto_amount,
            "crypto_currency": crypto,
            "exchange_rate": price,
            "fee_amount": fee,
            "fee_currency": fiat_currency,
            "fee_percentage": FEE_PERCENTAGE,
            "total_fiat": round(fiat_amount - fee, 2),
            "price_source": "fixed" if crypto == "NENO" else "coingecko"
        }


# Singleton instance
pricing_service = PricingService()
