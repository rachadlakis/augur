"""
FRED (St. Louis Fed) economic series. Used for the 10-year real yield that
drives gold. Read-only; returns nothing rather than guessing when unavailable.
"""

import json
import urllib.parse
import urllib.request

from providers.base import DataUnavailable

FRED_URL = "https://api.stlouisfed.org/fred/series/observations"
REAL_YIELD_10Y = "DFII10"  # 10-year TIPS yield, percent


def observations(series_id: str, api_key: str, limit: int = 40, opener=urllib.request.urlopen) -> list[float]:
    """Latest numeric observations, newest first. FRED marks missing days with '.'."""
    if not api_key:
        raise DataUnavailable("FRED key not configured")
    query = urllib.parse.urlencode({
        "series_id": series_id, "api_key": api_key, "file_type": "json", "sort_order": "desc", "limit": limit,
    })
    try:
        with opener(f"{FRED_URL}?{query}", timeout=10) as response:
            payload = json.load(response)
    except Exception as e:
        raise DataUnavailable(f"FRED request for {series_id} failed: {e}") from e
    values = [float(o["value"]) for o in payload.get("observations", []) if o.get("value") not in (None, ".")]
    if not values:
        raise DataUnavailable(f"FRED returned no data for {series_id}")
    return values


def real_yield_change_bps(api_key: str, lookback_days: int = 20, opener=urllib.request.urlopen) -> float:
    """Change in the 10y real yield over roughly `lookback_days` trading days, in basis points."""
    values = observations(REAL_YIELD_10Y, api_key, limit=lookback_days + 10, opener=opener)
    if len(values) <= lookback_days:
        raise DataUnavailable("not enough real-yield history")
    return (values[0] - values[lookback_days]) * 100.0
