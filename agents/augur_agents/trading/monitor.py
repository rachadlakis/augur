"""Position monitoring and thesis invalidation checks for active trades."""

from __future__ import annotations

from typing import Any


class PositionMonitor:
    """Track active positions against plan, thesis, and volatility conditions."""

    def evaluate(
        self,
        *,
        trade: dict[str, Any],
        current_price: float,
        market_snapshot: Any,
        volatility_spike: bool = False,
        news_impact: str = "low",
        thesis_valid: bool = True,
    ) -> dict[str, Any]:
        stop = float(trade.get("stop", 0.0) or 0.0)
        target = float(trade.get("target", 0.0) or 0.0)
        side = str(trade.get("side", "")).upper()

        if side in {"LONG", "BUY"}:
            hit_stop = stop > 0 and current_price <= stop
            hit_target = target > 0 and current_price >= target
        elif side in {"SHORT", "SELL"}:
            hit_stop = stop > 0 and current_price >= stop
            hit_target = target > 0 and current_price <= target
        else:
            return {
                "status": "REVIEW",
                "reason": f"unknown position side {trade.get('side')!r}; stops cannot be evaluated",
                "action": "monitor",
                "price": current_price,
            }

        if hit_stop:
            return {
                "status": "HIT_STOP",
                "reason": "price reached the pre-set stop level",
                "action": "exit",
                "price": current_price,
            }

        if hit_target:
            return {
                "status": "HIT_TARGET",
                "reason": "price met the pre-defined target",
                "action": "exit",
                "price": current_price,
            }

        if not thesis_valid:
            return {
                "status": "THESIS_INVALIDATED",
                "reason": trade.get("invalidation") or "original thesis no longer holds",
                "action": "exit",
                "price": current_price,
            }

        if volatility_spike or news_impact.upper() in {"HIGH", "MEDIUM"}:
            return {
                "status": "REVIEW",
                "reason": "volatility or event risk deserves a fresh review",
                "action": "monitor",
                "price": current_price,
            }

        return {
            "status": "ACTIVE",
            "reason": "thesis remains intact and no planned exit has fired",
            "action": "hold",
            "price": current_price,
        }
