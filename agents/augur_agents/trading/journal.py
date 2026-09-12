"""Trade journaling and post-trade review utilities."""

from __future__ import annotations

from typing import Any


class TradeJournal:
    """Record trades and summarize post-trade outcomes for review."""

    def __init__(self) -> None:
        self._trades: dict[str, dict[str, Any]] = {}

    def record_trade(self, trade: dict[str, Any]) -> dict[str, Any]:
        trade_id = f"trade_{len(self._trades) + 1:04d}"
        entry = float(trade.get("entry", 0.0) or 0.0)
        exit_price = float(trade.get("exit", entry) or entry)
        size = float(trade.get("size", 0.0) or 0.0)
        pnl = (exit_price - entry) * size if trade.get("side") == "LONG" else (entry - exit_price) * size
        record = {
            "trade_id": trade_id,
            "symbol": trade.get("symbol", "UNKNOWN"),
            "side": trade.get("side", "LONG"),
            "entry": entry,
            "exit": exit_price,
            "size": size,
            "thesis": trade.get("thesis", ""),
            "agent_outputs": trade.get("agent_outputs", []),
            "pnl": pnl,
        }
        self._trades[trade_id] = record
        return record

    def review_trade(self, trade_id: str, *, tags: list[str] | None = None) -> dict[str, Any]:
        trade = self._trades[trade_id]
        tags = tags or []
        outcome = "profitable" if trade["pnl"] > 0 else "loss" if trade["pnl"] < 0 else "flat"
        return {
            "trade_id": trade_id,
            "symbol": trade["symbol"],
            "outcome": outcome,
            "tags": tags,
            "pnl": trade["pnl"],
        }
