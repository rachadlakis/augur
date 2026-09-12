"""Weighted synthesis of agent evidence into a single decision."""

from __future__ import annotations

from typing import Any


class OrchestratorConsensus:
    """Combine specialist signals without majority-vote behavior."""

    _SIGNAL_STRENGTH = {
        "BUY": 1.0,
        "SELL": -1.0,
        "HOLD": 0.0,
        "NEUTRAL": 0.0,
        "NO_TRADE": 0.0,
    }

    def synthesize(self, agent_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        if not agent_outputs:
            return {
                "decision": "NO_TRADE",
                "score": 0.0,
                "conflict_penalty": 0.0,
                "reason": "no agent evidence supplied",
            }

        weighted_total = 0.0
        conflict_penalty = 0.0
        active_buys = 0
        active_sells = 0

        for output in agent_outputs:
            signal = str(output.get("signal", "NEUTRAL")).upper()
            confidence = float(output.get("confidence", 0.0))
            evidence_quality = float(output.get("evidence_quality", 0.5))
            data_freshness = float(output.get("data_freshness", 0.5))
            risk_flags = output.get("risk_flags") or []

            direction = self._SIGNAL_STRENGTH.get(signal, 0.0)
            weight = confidence * evidence_quality * data_freshness
            weighted_total += direction * weight

            if signal == "BUY":
                active_buys += 1
            elif signal == "SELL":
                active_sells += 1

            if any(flag in {"crowded", "conflict", "stale"} for flag in risk_flags):
                conflict_penalty += 0.10

        if active_buys and active_sells:
            conflict_penalty += 0.25

        if abs(weighted_total) < 0.25 or conflict_penalty >= 0.35:
            decision = "NO_TRADE"
        elif weighted_total > 0:
            decision = "BUY"
        elif weighted_total < 0:
            decision = "SELL"
        else:
            decision = "HOLD"

        if decision in {"BUY", "SELL"} and conflict_penalty >= 0.25:
            decision = "NO_TRADE"

        return {
            "decision": decision,
            "score": round(weighted_total, 4),
            "conflict_penalty": round(conflict_penalty, 4),
            "reason": "weighted evidence after conflict penalty",
        }
