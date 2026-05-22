"""
Market Data API Routes.

Provides endpoints for:
- Real-time cryptocurrency market data (30+ coins)
- Price, market cap, volume, % change
- Cached responses to avoid rate limits

Data source: CoinGecko API (free tier)
"""

from fastapi import APIRouter, HTTPException, Query
from datetime import datetime, timezone
import httpx
import asyncio
import logging

from database.mongodb import get_database

router = APIRouter(prefix="/market-data", tags=["Market Data"])
logger = logging.getLogger(__name__)

COINGECKO_BASE = "https://api.coingecko.com/api/v3"
CACHE_TTL_SECONDS = 120

_cache = {"data": None, "timestamp": None, "trending": None, "trending_ts": None}

TOP_COINS = [
    "bitcoin", "ethereum", "tether", "binancecoin", "solana",
    "ripple", "usd-coin", "cardano", "dogecoin", "avalanche-2",
    "polkadot", "chainlink", "polygon-ecosystem-token", "tron",
    "litecoin", "shiba-inu", "uniswap", "stellar", "cosmos",
    "near", "monero", "aptos", "internet-computer", "arbitrum",
    "optimism", "filecoin", "aave", "the-graph", "maker",
    "fantom", "algorand", "injective-protocol"
]


async def _fetch_from_coingecko(url: str, params: dict) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def _get_fallback_data(vs_currency: str) -> dict:
    """Static fallback data when CoinGecko is rate limited."""
    fallback_coins = [
        {"id": "bitcoin", "symbol": "BTC", "name": "Bitcoin", "image": "https://assets.coingecko.com/coins/images/1/small/bitcoin.png", "current_price": 60787, "market_cap": 1197000000000, "market_cap_rank": 1, "total_volume": 28500000000, "price_change_24h": 450.2, "price_change_percentage_24h": 0.75, "price_change_percentage_1h": 0.1, "price_change_percentage_7d": 2.3, "circulating_supply": 19700000, "total_supply": 21000000, "ath": 73750, "ath_change_percentage": -17.5, "sparkline_7d": [], "last_updated": None},
        {"id": "ethereum", "symbol": "ETH", "name": "Ethereum", "image": "https://assets.coingecko.com/coins/images/279/small/ethereum.png", "current_price": 1769, "market_cap": 213000000000, "market_cap_rank": 2, "total_volume": 12400000000, "price_change_24h": -12.5, "price_change_percentage_24h": -0.7, "price_change_percentage_1h": -0.2, "price_change_percentage_7d": -1.5, "circulating_supply": 120000000, "total_supply": None, "ath": 4878, "ath_change_percentage": -63.7, "sparkline_7d": [], "last_updated": None},
        {"id": "tether", "symbol": "USDT", "name": "Tether", "image": "https://assets.coingecko.com/coins/images/325/small/Tether.png", "current_price": 0.92, "market_cap": 120000000000, "market_cap_rank": 3, "total_volume": 55000000000, "price_change_24h": 0.001, "price_change_percentage_24h": 0.01, "price_change_percentage_1h": 0, "price_change_percentage_7d": 0.02, "circulating_supply": 130000000000, "total_supply": 130000000000, "ath": 1.32, "ath_change_percentage": -30.3, "sparkline_7d": [], "last_updated": None},
        {"id": "binancecoin", "symbol": "BNB", "name": "BNB", "image": "https://assets.coingecko.com/coins/images/825/small/bnb-icon2_2x.png", "current_price": 555.36, "market_cap": 83000000000, "market_cap_rank": 4, "total_volume": 1400000000, "price_change_24h": 3.2, "price_change_percentage_24h": 0.58, "price_change_percentage_1h": 0.05, "price_change_percentage_7d": 1.8, "circulating_supply": 149000000, "total_supply": 149000000, "ath": 686.31, "ath_change_percentage": -19.1, "sparkline_7d": [], "last_updated": None},
        {"id": "solana", "symbol": "SOL", "name": "Solana", "image": "https://assets.coingecko.com/coins/images/4128/small/solana.png", "current_price": 74.72, "market_cap": 36000000000, "market_cap_rank": 5, "total_volume": 2100000000, "price_change_24h": 1.5, "price_change_percentage_24h": 2.05, "price_change_percentage_1h": 0.3, "price_change_percentage_7d": 5.2, "circulating_supply": 481000000, "total_supply": 590000000, "ath": 259.96, "ath_change_percentage": -71.3, "sparkline_7d": [], "last_updated": None},
        {"id": "ripple", "symbol": "XRP", "name": "XRP", "image": "https://assets.coingecko.com/coins/images/44/small/xrp-symbol-white-128.png", "current_price": 0.52, "market_cap": 29000000000, "market_cap_rank": 6, "total_volume": 900000000, "price_change_24h": 0.01, "price_change_percentage_24h": 1.95, "price_change_percentage_1h": 0.1, "price_change_percentage_7d": 3.1, "circulating_supply": 55000000000, "total_supply": 100000000000, "ath": 3.40, "ath_change_percentage": -84.7, "sparkline_7d": [], "last_updated": None},
        {"id": "usd-coin", "symbol": "USDC", "name": "USD Coin", "image": "https://assets.coingecko.com/coins/images/6319/small/usdc.png", "current_price": 0.92, "market_cap": 25000000000, "market_cap_rank": 7, "total_volume": 4500000000, "price_change_24h": 0, "price_change_percentage_24h": 0.01, "price_change_percentage_1h": 0, "price_change_percentage_7d": 0, "circulating_supply": 27000000000, "total_supply": 27000000000, "ath": 1.17, "ath_change_percentage": -21.3, "sparkline_7d": [], "last_updated": None},
        {"id": "cardano", "symbol": "ADA", "name": "Cardano", "image": "https://assets.coingecko.com/coins/images/975/small/cardano.png", "current_price": 0.38, "market_cap": 13500000000, "market_cap_rank": 8, "total_volume": 300000000, "price_change_24h": 0.005, "price_change_percentage_24h": 1.33, "price_change_percentage_1h": 0.1, "price_change_percentage_7d": 2.1, "circulating_supply": 35500000000, "total_supply": 45000000000, "ath": 3.09, "ath_change_percentage": -87.7, "sparkline_7d": [], "last_updated": None},
        {"id": "dogecoin", "symbol": "DOGE", "name": "Dogecoin", "image": "https://assets.coingecko.com/coins/images/5/small/dogecoin.png", "current_price": 0.082, "market_cap": 12000000000, "market_cap_rank": 9, "total_volume": 500000000, "price_change_24h": 0.002, "price_change_percentage_24h": 2.5, "price_change_percentage_1h": 0.15, "price_change_percentage_7d": 4.2, "circulating_supply": 145000000000, "total_supply": None, "ath": 0.731, "ath_change_percentage": -88.8, "sparkline_7d": [], "last_updated": None},
        {"id": "avalanche-2", "symbol": "AVAX", "name": "Avalanche", "image": "https://assets.coingecko.com/coins/images/12559/small/Avalanche_Circle_RedWhite_Trans.png", "current_price": 18.50, "market_cap": 7500000000, "market_cap_rank": 10, "total_volume": 250000000, "price_change_24h": 0.45, "price_change_percentage_24h": 2.49, "price_change_percentage_1h": 0.2, "price_change_percentage_7d": 3.5, "circulating_supply": 405000000, "total_supply": 720000000, "ath": 144.96, "ath_change_percentage": -87.2, "sparkline_7d": [], "last_updated": None},
        {"id": "polkadot", "symbol": "DOT", "name": "Polkadot", "image": "https://assets.coingecko.com/coins/images/12171/small/polkadot.png", "current_price": 4.20, "market_cap": 6000000000, "market_cap_rank": 11, "total_volume": 150000000, "price_change_24h": 0.08, "price_change_percentage_24h": 1.94, "price_change_percentage_1h": 0.1, "price_change_percentage_7d": 2.8, "circulating_supply": 1430000000, "total_supply": 1430000000, "ath": 54.98, "ath_change_percentage": -92.4, "sparkline_7d": [], "last_updated": None},
        {"id": "chainlink", "symbol": "LINK", "name": "Chainlink", "image": "https://assets.coingecko.com/coins/images/877/small/chainlink-new-logo.png", "current_price": 12.50, "market_cap": 7800000000, "market_cap_rank": 12, "total_volume": 350000000, "price_change_24h": 0.30, "price_change_percentage_24h": 2.46, "price_change_percentage_1h": 0.15, "price_change_percentage_7d": 4.1, "circulating_supply": 626000000, "total_supply": 1000000000, "ath": 52.70, "ath_change_percentage": -76.3, "sparkline_7d": [], "last_updated": None},
        {"id": "polygon-ecosystem-token", "symbol": "POL", "name": "Polygon", "image": "https://assets.coingecko.com/coins/images/4713/small/polygon.png", "current_price": 0.25, "market_cap": 2500000000, "market_cap_rank": 13, "total_volume": 120000000, "price_change_24h": 0.005, "price_change_percentage_24h": 2.04, "price_change_percentage_1h": 0.1, "price_change_percentage_7d": 3.3, "circulating_supply": 10000000000, "total_supply": 10000000000, "ath": 2.92, "ath_change_percentage": -91.4, "sparkline_7d": [], "last_updated": None},
        {"id": "tron", "symbol": "TRX", "name": "TRON", "image": "https://assets.coingecko.com/coins/images/1094/small/tron-logo.png", "current_price": 0.10, "market_cap": 8700000000, "market_cap_rank": 14, "total_volume": 300000000, "price_change_24h": 0.001, "price_change_percentage_24h": 1.0, "price_change_percentage_1h": 0.05, "price_change_percentage_7d": 1.5, "circulating_supply": 86800000000, "total_supply": 86800000000, "ath": 0.2317, "ath_change_percentage": -56.8, "sparkline_7d": [], "last_updated": None},
        {"id": "litecoin", "symbol": "LTC", "name": "Litecoin", "image": "https://assets.coingecko.com/coins/images/2/small/litecoin.png", "current_price": 68.50, "market_cap": 5100000000, "market_cap_rank": 15, "total_volume": 280000000, "price_change_24h": 1.2, "price_change_percentage_24h": 1.78, "price_change_percentage_1h": 0.08, "price_change_percentage_7d": 2.5, "circulating_supply": 74500000, "total_supply": 84000000, "ath": 410.26, "ath_change_percentage": -83.3, "sparkline_7d": [], "last_updated": None},
        {"id": "shiba-inu", "symbol": "SHIB", "name": "Shiba Inu", "image": "https://assets.coingecko.com/coins/images/11939/small/shiba.png", "current_price": 0.0000089, "market_cap": 5200000000, "market_cap_rank": 16, "total_volume": 200000000, "price_change_24h": 0.0000001, "price_change_percentage_24h": 1.14, "price_change_percentage_1h": 0.05, "price_change_percentage_7d": 3.0, "circulating_supply": 589000000000000, "total_supply": 999991000000000, "ath": 0.0000861, "ath_change_percentage": -89.7, "sparkline_7d": [], "last_updated": None},
        {"id": "uniswap", "symbol": "UNI", "name": "Uniswap", "image": "https://assets.coingecko.com/coins/images/12504/small/uni.jpg", "current_price": 5.80, "market_cap": 3500000000, "market_cap_rank": 17, "total_volume": 120000000, "price_change_24h": 0.15, "price_change_percentage_24h": 2.65, "price_change_percentage_1h": 0.2, "price_change_percentage_7d": 4.8, "circulating_supply": 600000000, "total_supply": 1000000000, "ath": 44.97, "ath_change_percentage": -87.1, "sparkline_7d": [], "last_updated": None},
        {"id": "stellar", "symbol": "XLM", "name": "Stellar", "image": "https://assets.coingecko.com/coins/images/100/small/Stellar_symbol_black_RGB.png", "current_price": 0.095, "market_cap": 2800000000, "market_cap_rank": 18, "total_volume": 80000000, "price_change_24h": 0.002, "price_change_percentage_24h": 2.15, "price_change_percentage_1h": 0.1, "price_change_percentage_7d": 3.7, "circulating_supply": 29500000000, "total_supply": 50000000000, "ath": 0.938, "ath_change_percentage": -89.9, "sparkline_7d": [], "last_updated": None},
        {"id": "cosmos", "symbol": "ATOM", "name": "Cosmos", "image": "https://assets.coingecko.com/coins/images/1481/small/cosmos_hub.png", "current_price": 5.20, "market_cap": 2000000000, "market_cap_rank": 19, "total_volume": 90000000, "price_change_24h": 0.1, "price_change_percentage_24h": 1.96, "price_change_percentage_1h": 0.08, "price_change_percentage_7d": 2.9, "circulating_supply": 390000000, "total_supply": 390000000, "ath": 44.45, "ath_change_percentage": -88.3, "sparkline_7d": [], "last_updated": None},
        {"id": "near", "symbol": "NEAR", "name": "NEAR Protocol", "image": "https://assets.coingecko.com/coins/images/10365/small/near.jpg", "current_price": 2.80, "market_cap": 3100000000, "market_cap_rank": 20, "total_volume": 150000000, "price_change_24h": 0.08, "price_change_percentage_24h": 2.94, "price_change_percentage_1h": 0.15, "price_change_percentage_7d": 5.1, "circulating_supply": 1100000000, "total_supply": 1200000000, "ath": 20.44, "ath_change_percentage": -86.3, "sparkline_7d": [], "last_updated": None},
        {"id": "monero", "symbol": "XMR", "name": "Monero", "image": "https://assets.coingecko.com/coins/images/69/small/monero_logo.png", "current_price": 165.0, "market_cap": 3000000000, "market_cap_rank": 21, "total_volume": 60000000, "price_change_24h": 2.5, "price_change_percentage_24h": 1.54, "price_change_percentage_1h": 0.05, "price_change_percentage_7d": 1.2, "circulating_supply": 18400000, "total_supply": None, "ath": 542.33, "ath_change_percentage": -69.6, "sparkline_7d": [], "last_updated": None},
        {"id": "aptos", "symbol": "APT", "name": "Aptos", "image": "https://assets.coingecko.com/coins/images/26455/small/aptos_round.png", "current_price": 5.50, "market_cap": 2700000000, "market_cap_rank": 22, "total_volume": 100000000, "price_change_24h": 0.12, "price_change_percentage_24h": 2.23, "price_change_percentage_1h": 0.1, "price_change_percentage_7d": 3.8, "circulating_supply": 490000000, "total_supply": 1100000000, "ath": 19.92, "ath_change_percentage": -72.4, "sparkline_7d": [], "last_updated": None},
        {"id": "internet-computer", "symbol": "ICP", "name": "Internet Computer", "image": "https://assets.coingecko.com/coins/images/14495/small/Internet_Computer_logo.png", "current_price": 7.20, "market_cap": 3400000000, "market_cap_rank": 23, "total_volume": 55000000, "price_change_24h": 0.18, "price_change_percentage_24h": 2.56, "price_change_percentage_1h": 0.12, "price_change_percentage_7d": 4.5, "circulating_supply": 472000000, "total_supply": 520000000, "ath": 700.65, "ath_change_percentage": -98.97, "sparkline_7d": [], "last_updated": None},
        {"id": "arbitrum", "symbol": "ARB", "name": "Arbitrum", "image": "https://assets.coingecko.com/coins/images/16547/small/photo_2023-03-29_21.47.00.jpeg", "current_price": 0.55, "market_cap": 2200000000, "market_cap_rank": 24, "total_volume": 200000000, "price_change_24h": 0.01, "price_change_percentage_24h": 1.85, "price_change_percentage_1h": 0.08, "price_change_percentage_7d": 3.2, "circulating_supply": 4000000000, "total_supply": 10000000000, "ath": 2.39, "ath_change_percentage": -77.0, "sparkline_7d": [], "last_updated": None},
        {"id": "optimism", "symbol": "OP", "name": "Optimism", "image": "https://assets.coingecko.com/coins/images/25244/small/Optimism.png", "current_price": 1.30, "market_cap": 1600000000, "market_cap_rank": 25, "total_volume": 80000000, "price_change_24h": 0.03, "price_change_percentage_24h": 2.36, "price_change_percentage_1h": 0.1, "price_change_percentage_7d": 4.0, "circulating_supply": 1230000000, "total_supply": 4294000000, "ath": 4.85, "ath_change_percentage": -73.2, "sparkline_7d": [], "last_updated": None},
        {"id": "filecoin", "symbol": "FIL", "name": "Filecoin", "image": "https://assets.coingecko.com/coins/images/12817/small/filecoin.png", "current_price": 3.20, "market_cap": 1900000000, "market_cap_rank": 26, "total_volume": 70000000, "price_change_24h": 0.06, "price_change_percentage_24h": 1.91, "price_change_percentage_1h": 0.07, "price_change_percentage_7d": 2.6, "circulating_supply": 594000000, "total_supply": 1970000000, "ath": 236.84, "ath_change_percentage": -98.6, "sparkline_7d": [], "last_updated": None},
        {"id": "aave", "symbol": "AAVE", "name": "Aave", "image": "https://assets.coingecko.com/coins/images/12645/small/aave-token-round.png", "current_price": 82.0, "market_cap": 1200000000, "market_cap_rank": 27, "total_volume": 60000000, "price_change_24h": 1.8, "price_change_percentage_24h": 2.24, "price_change_percentage_1h": 0.1, "price_change_percentage_7d": 3.5, "circulating_supply": 14900000, "total_supply": 16000000, "ath": 661.69, "ath_change_percentage": -87.6, "sparkline_7d": [], "last_updated": None},
        {"id": "the-graph", "symbol": "GRT", "name": "The Graph", "image": "https://assets.coingecko.com/coins/images/13397/small/Graph_Token.png", "current_price": 0.12, "market_cap": 1100000000, "market_cap_rank": 28, "total_volume": 40000000, "price_change_24h": 0.003, "price_change_percentage_24h": 2.56, "price_change_percentage_1h": 0.12, "price_change_percentage_7d": 4.2, "circulating_supply": 9500000000, "total_supply": 10800000000, "ath": 2.84, "ath_change_percentage": -95.8, "sparkline_7d": [], "last_updated": None},
        {"id": "maker", "symbol": "MKR", "name": "Maker", "image": "https://assets.coingecko.com/coins/images/1364/small/Mark_Maker.png", "current_price": 1250.0, "market_cap": 1150000000, "market_cap_rank": 29, "total_volume": 50000000, "price_change_24h": 25.0, "price_change_percentage_24h": 2.04, "price_change_percentage_1h": 0.08, "price_change_percentage_7d": 3.1, "circulating_supply": 920000, "total_supply": 1005577, "ath": 6292.31, "ath_change_percentage": -80.1, "sparkline_7d": [], "last_updated": None},
        {"id": "fantom", "symbol": "FTM", "name": "Fantom", "image": "https://assets.coingecko.com/coins/images/4001/small/Fantom_round.png", "current_price": 0.28, "market_cap": 790000000, "market_cap_rank": 30, "total_volume": 45000000, "price_change_24h": 0.008, "price_change_percentage_24h": 2.94, "price_change_percentage_1h": 0.15, "price_change_percentage_7d": 5.0, "circulating_supply": 2800000000, "total_supply": 3175000000, "ath": 3.46, "ath_change_percentage": -91.9, "sparkline_7d": [], "last_updated": None},
        {"id": "algorand", "symbol": "ALGO", "name": "Algorand", "image": "https://assets.coingecko.com/coins/images/4380/small/download.png", "current_price": 0.14, "market_cap": 1100000000, "market_cap_rank": 31, "total_volume": 35000000, "price_change_24h": 0.003, "price_change_percentage_24h": 2.19, "price_change_percentage_1h": 0.1, "price_change_percentage_7d": 3.8, "circulating_supply": 8100000000, "total_supply": 10000000000, "ath": 3.28, "ath_change_percentage": -95.7, "sparkline_7d": [], "last_updated": None},
        {"id": "injective-protocol", "symbol": "INJ", "name": "Injective", "image": "https://assets.coingecko.com/coins/images/12882/small/Secondary_Symbol.png", "current_price": 12.80, "market_cap": 1200000000, "market_cap_rank": 32, "total_volume": 55000000, "price_change_24h": 0.35, "price_change_percentage_24h": 2.81, "price_change_percentage_1h": 0.12, "price_change_percentage_7d": 4.5, "circulating_supply": 93500000, "total_supply": 100000000, "ath": 52.62, "ath_change_percentage": -75.7, "sparkline_7d": [], "last_updated": None},
    ]
    from datetime import datetime, timezone
    return {
        "coins": fallback_coins,
        "total": len(fallback_coins),
        "vs_currency": vs_currency,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "fallback"
    }


@router.get("/coins")
async def get_market_data(
    vs_currency: str = Query("eur", description="Target currency"),
    page: int = Query(1, ge=1),
    per_page: int = Query(32, ge=1, le=100)
):
    """Get market data for 30+ cryptocurrencies."""
    now = datetime.now(timezone.utc)
    cache_key = f"{vs_currency}_{page}_{per_page}"

    if (
        _cache["data"]
        and _cache.get("key") == cache_key
        and _cache["timestamp"]
        and (now - _cache["timestamp"]).total_seconds() < CACHE_TTL_SECONDS
    ):
        return _cache["data"]

    try:
        ids_str = ",".join(TOP_COINS)
        data = await _fetch_from_coingecko(
            f"{COINGECKO_BASE}/coins/markets",
            {
                "vs_currency": vs_currency,
                "ids": ids_str,
                "order": "market_cap_desc",
                "per_page": per_page,
                "page": page,
                "sparkline": "true",
                "price_change_percentage": "1h,24h,7d"
            }
        )

        coins = []
        for c in data:
            coins.append({
                "id": c.get("id"),
                "symbol": c.get("symbol", "").upper(),
                "name": c.get("name"),
                "image": c.get("image"),
                "current_price": c.get("current_price"),
                "market_cap": c.get("market_cap"),
                "market_cap_rank": c.get("market_cap_rank"),
                "total_volume": c.get("total_volume"),
                "price_change_24h": c.get("price_change_24h"),
                "price_change_percentage_24h": c.get("price_change_percentage_24h"),
                "price_change_percentage_1h": c.get("price_change_percentage_1h_in_currency"),
                "price_change_percentage_7d": c.get("price_change_percentage_7d_in_currency"),
                "circulating_supply": c.get("circulating_supply"),
                "total_supply": c.get("total_supply"),
                "ath": c.get("ath"),
                "ath_change_percentage": c.get("ath_change_percentage"),
                "sparkline_7d": c.get("sparkline_in_7d", {}).get("price", []),
                "last_updated": c.get("last_updated"),
            })

        result = {
            "coins": coins,
            "total": len(coins),
            "vs_currency": vs_currency,
            "updated_at": now.isoformat()
        }
        _cache["data"] = result
        _cache["timestamp"] = now
        _cache["key"] = cache_key
        return result

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            if _cache["data"]:
                return _cache["data"]
            return _get_fallback_data(vs_currency)
        raise HTTPException(status_code=502, detail="Market data service unavailable")
    except Exception as e:
        logger.error(f"Market data fetch error: {e}")
        if _cache["data"]:
            return _cache["data"]
        return _get_fallback_data(vs_currency)


@router.get("/coin/{coin_id}")
async def get_coin_detail(coin_id: str):
    """Get detailed data for a specific coin."""
    try:
        data = await _fetch_from_coingecko(
            f"{COINGECKO_BASE}/coins/{coin_id}",
            {
                "localization": "false",
                "tickers": "false",
                "community_data": "false",
                "developer_data": "false",
                "sparkline": "true"
            }
        )
        return {
            "id": data.get("id"),
            "symbol": data.get("symbol", "").upper(),
            "name": data.get("name"),
            "image": data.get("image", {}).get("large"),
            "description": data.get("description", {}).get("en", "")[:500],
            "market_data": {
                "current_price": data.get("market_data", {}).get("current_price", {}),
                "market_cap": data.get("market_data", {}).get("market_cap", {}),
                "total_volume": data.get("market_data", {}).get("total_volume", {}),
                "price_change_24h": data.get("market_data", {}).get("price_change_24h"),
                "price_change_percentage_24h": data.get("market_data", {}).get("price_change_percentage_24h"),
                "price_change_percentage_7d": data.get("market_data", {}).get("price_change_percentage_7d"),
                "circulating_supply": data.get("market_data", {}).get("circulating_supply"),
                "total_supply": data.get("market_data", {}).get("total_supply"),
                "ath": data.get("market_data", {}).get("ath", {}),
            },
            "categories": data.get("categories", []),
            "links": {
                "homepage": data.get("links", {}).get("homepage", [None])[0],
                "blockchain_site": [s for s in data.get("links", {}).get("blockchain_site", []) if s][:3],
            }
        }
    except Exception as e:
        logger.error(f"Coin detail fetch error: {e}")
        raise HTTPException(status_code=502, detail="Coin data unavailable")


@router.get("/trending")
async def get_trending():
    """Get trending coins."""
    now = datetime.now(timezone.utc)
    if (
        _cache["trending"]
        and _cache["trending_ts"]
        and (now - _cache["trending_ts"]).total_seconds() < 300
    ):
        return _cache["trending"]

    try:
        data = await _fetch_from_coingecko(f"{COINGECKO_BASE}/search/trending", {})
        coins = []
        for item in data.get("coins", [])[:10]:
            c = item.get("item", {})
            coins.append({
                "id": c.get("id"),
                "symbol": c.get("symbol", "").upper(),
                "name": c.get("name"),
                "market_cap_rank": c.get("market_cap_rank"),
                "thumb": c.get("thumb"),
                "score": c.get("score"),
            })
        result = {"trending": coins, "updated_at": now.isoformat()}
        _cache["trending"] = result
        _cache["trending_ts"] = now
        return result
    except Exception as e:
        logger.error(f"Trending fetch error: {e}")
        if _cache["trending"]:
            return _cache["trending"]
        raise HTTPException(status_code=502, detail="Trending data unavailable")
