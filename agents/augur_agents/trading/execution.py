"""Execution planning for paper-trading and live execution."""

from __future__ import annotations

from typing import Any


def recent_move(market_snapshot: Any, timeframe: str = "1h") -> float | None:
    """Fractional open-to-close move of the latest bar, or None when unavailable."""
    ohlcv = getattr(market_snapshot, "ohlcv", None) or {}
    bar = ohlcv.get(timeframe) or {}
    open_price = float(bar.get("open", 0.0) or 0.0)
    close_price = float(bar.get("close", 0.0) or 0.0)
    if open_price <= 0 or close_price <= 0:
        return None
    return close_price / open_price - 1.0


class ExecutionPlanner:
    """Determines if a trade can be executed safely at this moment.

    Every entry is planned as a bracket: the stop-loss and take-profit travel
    with the entry order so a position is never open without protection.
    Entries that chase a large move in the trade direction are refused, because
    those entries underperform random selection in production records.
    """

    def __init__(
        self,
        *,
        max_spread: float = 0.002,
        max_slippage: float = 0.002,
        min_liquidity: float = 0.20,
        max_signal_age_seconds: float = 20.0,
        max_chase_move: float = 0.0075,
    ) -> None:
        self.max_spread = max_spread
        self.max_slippage = max_slippage
        self.min_liquidity = min_liquidity
        self.max_signal_age_seconds = max_signal_age_seconds
        self.max_chase_move = max_chase_move

    def plan(
        self,
        *,
        decision: str,
        market_snapshot: Any,
        spread: float,
        expected_slippage: float,
        liquidity: float,
        size: float,
        stop: float,
        signal_age_seconds: float,
        target: float | None = None,
        market_open: bool = True,
        exchange_healthy: bool = True,
    ) -> dict[str, Any]:
        reasons: list[str] = []

        if decision not in {"BUY", "SELL", "HOLD", "NO_TRADE"}:
            reasons.append("unknown trade decision")

        if decision in {"BUY", "SELL"}:
            if not market_open:
                reasons.append("market is not open")
            if not exchange_healthy:
                reasons.append("exchange health check failed")
            if size <= 0:
                reasons.append("position size must be positive")
            if stop <= 0:
                reasons.append("stop must be defined")
            if target is None or target <= 0:
                reasons.append("take-profit must be defined for a bracketed entry")
            if spread > self.max_spread:
                reasons.append("spread exceeds configured maximum")
            if expected_slippage > self.max_slippage:
                reasons.append("expected slippage exceeds configured maximum")
            if liquidity < self.min_liquidity:
                reasons.append("liquidity below configured minimum")
            if signal_age_seconds > self.max_signal_age_seconds:
                reasons.append("signal is stale")

            move = recent_move(market_snapshot)
            if move is not None:
                aligned_move = move if decision == "BUY" else -move
                if aligned_move > self.max_chase_move:
                    reasons.append("entry chases a recent move in the trade direction")

        is_entry = decision in {"BUY", "SELL"}
        return {
            "allowed": not reasons,
            "reasons": reasons,
            "order_type": "market" if is_entry else "hold",
            "protection": {"stop_loss": stop, "take_profit": target} if is_entry else None,
        }
