"""The tradable universe (crypto, gold, silver, oil, equities) and snapshot building.

Commodities are traded through liquid exchange-traded funds so one broker
account covers everything. The fund structure matters: physically backed gold
and silver funds hold metal, while oil funds hold futures and pay roll costs.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from ..contracts import MarketSnapshot


@dataclass(frozen=True)
class Instrument:
    symbol: str
    name: str
    asset_class: str          # "crypto" | "commodity" | "equity"
    underlying: str           # "bitcoin", "gold", "oil", ...
    venue: str                # "alpaca" | "binance"
    physically_backed: bool = False
    note: str = ""


UNIVERSE: tuple[Instrument, ...] = (
    Instrument("BTC/USD", "Bitcoin", "crypto", "bitcoin", "alpaca", note="Trades 24/7"),
    Instrument("ETH/USD", "Ethereum", "crypto", "ethereum", "alpaca", note="Trades 24/7"),
    Instrument("SOL/USD", "Solana", "crypto", "solana", "alpaca", note="Trades 24/7; more volatile"),
    Instrument("GLD", "Gold (SPDR Gold Shares)", "commodity", "gold", "alpaca", physically_backed=True,
               note="Holds physical gold; no futures roll"),
    Instrument("IAU", "Gold (iShares Gold Trust)", "commodity", "gold", "alpaca", physically_backed=True,
               note="Holds physical gold; lower fee than GLD"),
    Instrument("SLV", "Silver (iShares Silver Trust)", "commodity", "silver", "alpaca", physically_backed=True,
               note="Holds physical silver"),
    Instrument("USO", "Crude oil (WTI, United States Oil Fund)", "commodity", "oil", "alpaca",
               note="Holds oil futures; contango drags on long holders"),
    Instrument("BNO", "Crude oil (Brent, United States Brent Oil Fund)", "commodity", "oil", "alpaca",
               note="Holds Brent futures; same roll risk as USO"),
    Instrument("SPY", "US stock market (S&P 500)", "equity", "stocks", "alpaca", note="The benchmark to beat"),
)

BY_SYMBOL = {instrument.symbol: instrument for instrument in UNIVERSE}


def _aggregate(bars: list[dict[str, Any]]) -> dict[str, float]:
    return {
        "open": float(bars[0]["open"]),
        "high": max(float(b["high"]) for b in bars),
        "low": min(float(b["low"]) for b in bars),
        "close": float(bars[-1]["close"]),
        "volume": sum(float(b.get("volume", 0.0) or 0.0) for b in bars),
    }


def average_true_range(bars: list[dict[str, Any]], period: int = 14) -> float:
    """Wilder-style ATR as a simple mean of true ranges over the last `period` bars."""
    if len(bars) < 2:
        return 0.0
    ranges = []
    for previous, bar in zip(bars, bars[1:]):
        high, low, prior_close = float(bar["high"]), float(bar["low"]), float(previous["close"])
        ranges.append(max(high - low, abs(high - prior_close), abs(low - prior_close)))
    window = ranges[-period:]
    return sum(window) / len(window)


def snapshot_from_bars(
    symbol: str,
    hourly: list[dict[str, Any]],
    daily: list[dict[str, Any]],
    *,
    spread: float = 0.0005,
    liquidity: float = 0.9,
) -> MarketSnapshot:
    """Build the pipeline's MarketSnapshot from raw OHLC bars (oldest first).

    1h is the latest hourly bar, 4h the last four aggregated, 1d the latest
    daily bar. ATR comes from daily bars, matching the 4h-24h holding horizon.
    """
    if not hourly or not daily:
        raise ValueError(f"need hourly and daily bars for {symbol}")
    last_hour = hourly[-1]
    timestamp = last_hour.get("timestamp") or datetime.now(timezone.utc)
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return MarketSnapshot(
        asset=symbol,
        timestamp=timestamp,
        price=float(last_hour["close"]),
        ohlcv={
            "1h": _aggregate(hourly[-1:]),
            "4h": _aggregate(hourly[-4:]),
            "1d": _aggregate(daily[-1:]),
        },
        volume=float(last_hour.get("volume", 0.0) or 0.0),
        spread=spread,
        liquidity=liquidity,
        volatility={"atr": average_true_range(daily)},
    )
