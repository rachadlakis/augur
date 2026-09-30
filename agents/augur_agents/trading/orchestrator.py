"""Weighted synthesis of agent evidence into a single decision."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .calibration import SpecialistCalibrator

CONSENSUS_AGENT = "consensus"


class OrchestratorConsensus:
    """Combine specialist signals without majority-vote behavior.

    With a `SpecialistCalibrator`, stated confidences are replaced by measured
    hit rates and each agent is weighted by its realized information
    coefficient. The consensus score itself is calibrated the same way under the
    `consensus` key, which yields `win_probability` for meta-label sizing.
    """

    _SIGNAL_STRENGTH = {
        "BUY": 1.0,
        "SELL": -1.0,
        "HOLD": 0.0,
        "NEUTRAL": 0.0,
        "NO_TRADE": 0.0,
    }

    _QUALITY_LABELS = {"HIGH": 0.9, "MEDIUM": 0.6, "LOW": 0.3}

    def __init__(
        self,
        *,
        calibrator: SpecialistCalibrator | None = None,
        freshness_horizon_seconds: float = 3600.0,
    ) -> None:
        self.calibrator = calibrator
        self.freshness_horizon_seconds = freshness_horizon_seconds

    def _unit(self, value: Any, default: float) -> float:
        """Accept 0-1 floats, HIGH/MEDIUM/LOW labels, or a timestamp (decayed to freshness)."""
        if value is None:
            return default
        if isinstance(value, str):
            label = value.strip().upper()
            if label in self._QUALITY_LABELS:
                return self._QUALITY_LABELS[label]
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                return default
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            age = (datetime.now(timezone.utc) - value).total_seconds()
            return max(0.0, min(1.0, 1.0 - age / self.freshness_horizon_seconds))
        return max(0.0, min(1.0, float(value)))

    def synthesize(self, agent_outputs: list[dict[str, Any]]) -> dict[str, Any]:
        if not agent_outputs:
            return {
                "decision": "NO_TRADE",
                "score": 0.0,
                "conflict_penalty": 0.0,
                "reason": "no agent evidence supplied",
                "win_probability": None,
            }

        weighted_total = 0.0
        conflict_penalty = 0.0
        active_buys = 0
        active_sells = 0

        for output in agent_outputs:
            agent = str(output.get("agent", "unknown"))
            signal = str(output.get("signal", "NEUTRAL")).upper()
            confidence = float(output.get("confidence", 0.0))
            evidence_quality = self._unit(output.get("evidence_quality"), 0.5)
            data_freshness = self._unit(output.get("data_freshness"), 0.5)
            risk_flags = output.get("risk_flags") or []

            agent_weight = 1.0
            if self.calibrator is not None:
                confidence = self.calibrator.calibrate(agent, confidence)
                agent_weight = self.calibrator.weight(agent)

            direction = self._SIGNAL_STRENGTH.get(signal, 0.0)
            weight = confidence * evidence_quality * data_freshness * agent_weight
            weighted_total += direction * weight

            if signal == "BUY" and weight > 0:
                active_buys += 1
            elif signal == "SELL" and weight > 0:
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

        win_probability = None
        if self.calibrator is not None and self.calibrator.is_calibrated(CONSENSUS_AGENT):
            win_probability = self.calibrator.calibrate(CONSENSUS_AGENT, abs(weighted_total))

        return {
            "decision": decision,
            "score": round(weighted_total, 4),
            "conflict_penalty": round(conflict_penalty, 4),
            "reason": "weighted evidence after conflict penalty",
            "win_probability": win_probability,
        }
