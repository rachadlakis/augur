"""Crypto market research tools using CoinGecko API (free, no auth needed).

Real-time crypto market data, trending coins, news sentiment, and on-chain metrics.
These tools stand in for a ``crypto-research-mcp`` and can be swapped for a 
real MCP server without changing the agent interface.

CoinGecko API: https://www.coingecko.com/api/documentation
- No authentication required
- Free tier: 10-50 calls/minute
- Data: Prices, market cap, volume, trending coins, top gainers/losers
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import requests

logger = logging.getLogger(__name__)

# CoinGecko API endpoints (free tier)
COINGECKO_BASE = "https://api.coingecko.com/api/v3"
TIMEOUT = 10


class CoinGeckoClient:
    """CoinGecko API client for crypto market research."""
    
    def __init__(self, rate_limit_delay: float = 0.1):
        """Initialize with rate limiting to respect free tier."""
        self.rate_limit_delay = rate_limit_delay
        self.last_request_time = 0
    
    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit_delay:
            time.sleep(self.rate_limit_delay - elapsed)
        self.last_request_time = time.time()
    
    def _get(self, endpoint: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make GET request with rate limiting."""
        self._rate_limit()
        url = f"{COINGECKO_BASE}{endpoint}"
        try:
            response = requests.get(url, params=params, timeout=TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            logger.error(f"CoinGecko API error: {e}")
            return {}
    
    def get_trending_coins(self, limit: int = 7) -> list[dict[str, Any]]:
        """Get trending coins in last 24h."""
        data = self._get("/search/trending")
        coins = []
        for item in data.get("coins", [])[:limit]:
            coin = item.get("item", {})
            coins.append({
                "symbol": coin.get("symbol", "").upper(),
                "name": coin.get("name", ""),
                "market_cap_rank": coin.get("market_cap_rank"),
                "price_btc": coin.get("price_btc"),
                "data": coin.get("data", {}),
            })
        return coins
    
    def get_top_gainers(self, vs_currency: str = "usd", limit: int = 10) -> list[dict[str, Any]]:
        """Get top gainers in last 24h."""
        data = self._get(
            "/coins/markets",
            params={
                "vs_currency": vs_currency,
                "order": "price_change_24h_desc",
                "per_page": limit,
                "sparkline": False,
            }
        )
        return [
            {
                "symbol": coin.get("symbol", "").upper(),
                "name": coin.get("name", ""),
                "price": coin.get("current_price"),
                "price_change_24h": coin.get("price_change_percentage_24h"),
                "market_cap": coin.get("market_cap"),
                "volume_24h": coin.get("total_volume"),
            }
            for coin in data if coin.get("symbol")
        ]
    
    def get_top_losers(self, vs_currency: str = "usd", limit: int = 10) -> list[dict[str, Any]]:
        """Get top losers in last 24h."""
        data = self._get(
            "/coins/markets",
            params={
                "vs_currency": vs_currency,
                "order": "price_change_24h_asc",
                "per_page": limit,
                "sparkline": False,
            }
        )
        return [
            {
                "symbol": coin.get("symbol", "").upper(),
                "name": coin.get("name", ""),
                "price": coin.get("current_price"),
                "price_change_24h": coin.get("price_change_percentage_24h"),
                "market_cap": coin.get("market_cap"),
                "volume_24h": coin.get("total_volume"),
            }
            for coin in data if coin.get("symbol")
        ]
    
    def get_market_overview(self) -> dict[str, Any]:
        """Get global crypto market data."""
        data = self._get("/global")
        return {
            "total_market_cap": data.get("total_market_cap", {}),
            "total_24h_vol": data.get("total_24h_vol", {}),
            "btc_dominance": data.get("btc_market_cap_percentage", {}).get("btc"),
            "eth_dominance": data.get("btc_market_cap_percentage", {}).get("eth"),
            "market_cap_change_24h": data.get("market_cap_change_percentage_24h_usd"),
            "active_cryptocurrencies": data.get("active_cryptocurrencies"),
        }
    
    def get_coin_data(self, coin_id: str) -> dict[str, Any]:
        """Get detailed data for a specific coin."""
        data = self._get(
            f"/coins/{coin_id}",
            params={"localization": False, "tickers": False, "market_data": True}
        )
        if not data:
            return {}
        
        return {
            "id": data.get("id"),
            "symbol": data.get("symbol", "").upper(),
            "name": data.get("name"),
            "description": data.get("description", {}).get("en", "")[:200],  # First 200 chars
            "links": data.get("links", {}),
            "market_data": {
                "current_price": data.get("market_data", {}).get("current_price", {}),
                "market_cap": data.get("market_data", {}).get("market_cap", {}),
                "ath": data.get("market_data", {}).get("ath", {}),
                "atl": data.get("market_data", {}).get("atl", {}),
                "price_change_24h": data.get("market_data", {}).get("price_change_24h_usd"),
                "price_change_7d": data.get("market_data", {}).get("price_change_percentage_7d_usd"),
                "price_change_30d": data.get("market_data", {}).get("price_change_percentage_30d_usd"),
            },
            "community_data": {
                "twitter_followers": data.get("community_data", {}).get("twitter_followers"),
                "reddit_subscribers": data.get("community_data", {}).get("reddit_subscribers"),
            },
        }
    
    def search_coins(self, query: str) -> list[dict[str, Any]]:
        """Search for coins by name or symbol."""
        data = self._get("/search", params={"query": query})
        coins = []
        for item in data.get("coins", [])[:10]:
            coins.append({
                "symbol": item.get("symbol", "").upper(),
                "name": item.get("name", ""),
                "market_cap_rank": item.get("market_cap_rank"),
                "id": item.get("id"),
            })
        return coins


# Global client instance
_client: Optional[CoinGeckoClient] = None


def get_client() -> CoinGeckoClient:
    """Get or create CoinGecko client."""
    global _client
    if _client is None:
        _client = CoinGeckoClient()
    return _client


# ============================================================================
# Tool Functions (Agent Interface)
# ============================================================================

def research_trending_coins(limit: int = 7) -> dict[str, Any]:
    """
    Research trending cryptocurrencies in the last 24 hours.
    
    Returns market cap rank, recent trends, and basic metrics for each trending coin.
    Useful for identifying emerging projects gaining community attention.
    
    Args:
        limit: Number of trending coins to return (default: 7)
    
    Returns:
        Dict with list of trending coins and metadata
    """
    client = get_client()
    coins = client.get_trending_coins(limit)
    return {
        "status": "success" if coins else "no_data",
        "timestamp": time.time(),
        "trending_coins": coins,
        "note": "Data from CoinGecko (24h trending). Use for emerging project discovery.",
    }


def research_market_movers(direction: str = "gainers", limit: int = 10) -> dict[str, Any]:
    """
    Research top price movers (gainers or losers) in the last 24 hours.
    
    Identifies coins with strongest directional moves, useful for momentum analysis
    and detecting potential reversal candidates.
    
    Args:
        direction: "gainers" or "losers"
        limit: Number of coins to return
    
    Returns:
        Dict with list of top movers and their 24h performance
    """
    client = get_client()
    
    if direction.lower() == "losers":
        coins = client.get_top_losers(limit=limit)
    else:
        coins = client.get_top_gainers(limit=limit)
    
    return {
        "status": "success" if coins else "no_data",
        "timestamp": time.time(),
        "direction": direction,
        "coins": coins,
        "note": f"Top {direction} by 24h price change. Use for momentum/reversal signals.",
    }


def research_market_overview() -> dict[str, Any]:
    """
    Get global cryptocurrency market overview.
    
    Provides total market cap, dominance metrics, and overall market sentiment.
    Use for macro-level analysis (bull/bear phase, BTC dominance, etc.).
    
    Returns:
        Global market metrics
    """
    client = get_client()
    overview = client.get_market_overview()
    return {
        "status": "success" if overview else "no_data",
        "timestamp": time.time(),
        "market_overview": overview,
        "note": "Global crypto market metrics. Use for macro trend analysis.",
    }


def research_coin(coin_id: str) -> dict[str, Any]:
    """
    Research a specific cryptocurrency by ID (e.g., "bitcoin", "ethereum", "solana").
    
    Returns detailed data including description, links, market performance,
    and community metrics (Twitter, Reddit followers).
    
    Args:
        coin_id: CoinGecko coin ID (e.g., "bitcoin", "ethereum")
    
    Returns:
        Comprehensive coin data including fundamentals and social metrics
    """
    client = get_client()
    coin_data = client.get_coin_data(coin_id)
    
    if not coin_data:
        return {
            "status": "error",
            "timestamp": time.time(),
            "coin_id": coin_id,
            "note": f"Coin '{coin_id}' not found. Use research_search_coins() to find IDs.",
        }
    
    return {
        "status": "success",
        "timestamp": time.time(),
        "coin": coin_data,
        "note": "Detailed coin data including fundamentals. Use for project evaluation.",
    }


def research_search_coins(query: str) -> dict[str, Any]:
    """
    Search for cryptocurrencies by name or symbol.
    
    Helps find the correct CoinGecko coin ID for use with research_coin().
    
    Args:
        query: Search term (e.g., "Solana", "SOL", "Cardano")
    
    Returns:
        List of matching coins with their IDs
    """
    client = get_client()
    coins = client.search_coins(query)
    return {
        "status": "success" if coins else "no_data",
        "timestamp": time.time(),
        "query": query,
        "results": coins,
        "note": "Use 'id' value for research_coin(). E.g., research_coin('solana')",
    }


def research_crypto_sentiment(keywords: list[str]) -> dict[str, Any]:
    """
    Analyze crypto market sentiment based on trending data.
    
    Combines trending coins, market movers, and market dominance to assess
    overall market sentiment and identify hot sectors.
    
    Args:
        keywords: Optional sectors to focus on (e.g., ["layer2", "defi", "ai"])
    
    Returns:
        Sentiment analysis with identified trends and opportunities
    """
    client = get_client()
    
    # Gather data
    trending = client.get_trending_coins(limit=10)
    gainers = client.get_top_gainers(limit=10)
    market = client.get_market_overview()
    
    # Analyze sentiment
    btc_dominance = market.get("btc_dominance", 0)
    altseason = btc_dominance < 50 if btc_dominance else None
    
    sentiment = "ALTSEASON" if altseason else "BITCOIN_DOMINANT" if altseason is False else "NEUTRAL"
    
    return {
        "status": "success",
        "timestamp": time.time(),
        "sentiment": sentiment,
        "btc_dominance": btc_dominance,
        "market_cap_change_24h": market.get("market_cap_change_24h_usd"),
        "trending_coins": trending,
        "top_gainers": gainers,
        "note": "Synthesized sentiment from multiple data points. Use for macro-level decisions.",
    }


# ============================================================================
# Tool Registry
# ============================================================================

CRYPTO_RESEARCH_TOOLS = [
    research_trending_coins,
    research_market_movers,
    research_market_overview,
    research_coin,
    research_search_coins,
    research_crypto_sentiment,
]

__all__ = [
    "research_trending_coins",
    "research_market_movers",
    "research_market_overview",
    "research_coin",
    "research_search_coins",
    "research_crypto_sentiment",
    "CRYPTO_RESEARCH_TOOLS",
]
