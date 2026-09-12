"""Execution planning for paper-trading and live execution."""

from __future__ import annotations

from typing import Any


class ExecutionPlanner:
    """Determines if a trade can be executed safely at this moment."""

    def __init__(
        self,
        *,
        max_spread: float = 0.002,
        max_slippage: float = 0.002,
        min_liquidity: float = 0.20,
        max_signal_age_seconds: float = 20.0,
    ) -> None:
        self.max_spread = max_spread
        self.max_slippage = max_slippage
        self.min_liquidity = min_liquidity
        self.max_signal_age_seconds = max_signal_age_seconds

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
            if spread > self.max_spread:
                reasons.append("spread exceeds configured maximum")
            if expected_slippage > self.max_slippage:
                reasons.append("expected slippage exceeds configured maximum")
            if liquidity < self.min_liquidity:
                reasons.append("liquidity below configured minimum")
            if signal_age_seconds > self.max_signal_age_seconds:
                reasons.append("signal is stale")

        return {
            "allowed": not reasons,
            "reasons": reasons,
            "order_type": "stop_market" if decision in {"BUY", "SELL"} else "hold",
        }
