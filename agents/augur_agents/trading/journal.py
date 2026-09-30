"""Trade journaling and post-trade review utilities.

The journal doubles as a decision-provenance ledger: each trade can carry the
exact inputs the decision saw, plus the prompt-template, config and model
versions in force. That is what makes decisions replayable, comparable across
models, and usable later as fine-tuning data. P&L comes from reconstructed
fills, never from agent-reported numbers.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def input_hash(inputs: Any) -> str:
    """Stable SHA-256 of the decision inputs, for replay and dedup."""
    payload = json.dumps(inputs, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class TradeJournal:
    """Record trades and summarize post-trade outcomes for review."""

    def __init__(self) -> None:
        self._trades: dict[str, dict[str, Any]] = {}

    def record_trade(self, trade: dict[str, Any], *, provenance: dict[str, Any] | None = None) -> dict[str, Any]:
        """`provenance` may hold `inputs` (hashed and stored), `template_version`,
        `config_version`, `model`, and `fills` (list of {price, qty, fee})."""
        trade_id = f"trade_{len(self._trades) + 1:04d}"
        entry = float(trade.get("entry", 0.0) or 0.0)
        exit_price = float(trade.get("exit", entry) or entry)
        size = float(trade.get("size", 0.0) or 0.0)
        fees = float(trade.get("fees", 0.0) or 0.0)
        is_long = trade.get("side", "LONG") in {"LONG", "BUY"}
        gross = (exit_price - entry) * size if is_long else (entry - exit_price) * size

        provenance = dict(provenance or {})
        inputs = provenance.pop("inputs", None)
        record = {
            "trade_id": trade_id,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "symbol": trade.get("symbol", "UNKNOWN"),
            "side": trade.get("side", "LONG"),
            "entry": entry,
            "exit": exit_price,
            "size": size,
            "thesis": trade.get("thesis", ""),
            "agent_outputs": trade.get("agent_outputs", []),
            "fees": fees,
            "pnl": gross - fees,
            "provenance": {
                "input_hash": input_hash(inputs) if inputs is not None else None,
                "inputs": inputs,
                "template_version": provenance.pop("template_version", None),
                "config_version": provenance.pop("config_version", None),
                "model": provenance.pop("model", None),
                "fills": provenance.pop("fills", []),
                **provenance,
            },
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

    def ledger(self) -> list[dict[str, Any]]:
        return list(self._trades.values())

    def export_jsonl(self, path: str | Path) -> int:
        """Append every record as one JSON line; returns the number written."""
        records = self.ledger()
        with Path(path).open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, default=str) + "\n")
        return len(records)
