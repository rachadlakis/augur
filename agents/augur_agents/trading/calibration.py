"""Outcome-based calibration of specialist confidence.

LLM-stated confidence is not informative on its own: models report 0.8-0.9
regardless of domain, and their allocations diverge from their stated analysis.
This module replaces stated confidence with measured hit rates and weights each
specialist by its realized information coefficient (IC), so the orchestrator's
weights are learned from outcomes instead of hand-set.

Everything here is stdlib-only and deterministic.
"""

from __future__ import annotations

import bisect
import math
from collections import deque
from dataclasses import dataclass
from typing import Any

_DIRECTION = {"BUY": 1.0, "SELL": -1.0}


def isotonic_fit(xs: list[float], ys: list[float]) -> tuple[list[float], list[float]]:
    """Pool-adjacent-violators fit of a non-decreasing step function.

    Returns (thresholds, values): an input x maps to the value of the last
    threshold <= x (or the first value when x is below every threshold).
    """
    if len(xs) != len(ys):
        raise ValueError("xs and ys must be the same length")
    if not xs:
        return [], []

    pairs = sorted(zip(xs, ys))
    # Each block: [min_x, sum_y, count]
    blocks: list[list[float]] = []
    for x, y in pairs:
        if blocks and blocks[-1][0] == x:
            # Tied inputs must share one fitted value.
            blocks[-1][1] += y
            blocks[-1][2] += 1.0
        else:
            blocks.append([x, y, 1.0])
        while len(blocks) > 1 and blocks[-2][1] / blocks[-2][2] > blocks[-1][1] / blocks[-1][2]:
            _, y_sum, count = blocks.pop()
            blocks[-1][1] += y_sum
            blocks[-1][2] += count
    return [b[0] for b in blocks], [b[1] / b[2] for b in blocks]


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        return 0.0
    return cov / math.sqrt(var_x * var_y)


@dataclass(frozen=True)
class _Outcome:
    confidence: float
    direction: float
    forward_return: float

    @property
    def correct(self) -> float:
        return 1.0 if self.direction * self.forward_return > 0 else 0.0


class SpecialistCalibrator:
    """Rolling per-agent record of (signal, confidence) against realized returns.

    Until an agent has `min_samples` directional outcomes, its raw confidence and
    a neutral weight of 1.0 pass through unchanged. Returns must be measured at
    the horizon the signal claims, and be net of costs.
    """

    def __init__(self, *, window: int = 500, min_samples: int = 50, target_ic: float = 0.05) -> None:
        self.window = window
        self.min_samples = min_samples
        # An IC around 0.05 is already strong for a single short-horizon signal.
        self.target_ic = target_ic
        self._outcomes: dict[str, deque[_Outcome]] = {}
        self._fits: dict[str, tuple[list[float], list[float]]] = {}

    def record(self, agent: str, signal: str, confidence: float, forward_return: float) -> None:
        direction = _DIRECTION.get(str(signal).upper())
        if direction is None:
            return  # non-directional signals carry no testable claim
        history = self._outcomes.setdefault(agent, deque(maxlen=self.window))
        history.append(_Outcome(float(confidence), direction, float(forward_return)))
        self._fits.pop(agent, None)

    def samples(self, agent: str) -> int:
        return len(self._outcomes.get(agent, ()))

    def is_calibrated(self, agent: str) -> bool:
        return self.samples(agent) >= self.min_samples

    def calibrate(self, agent: str, confidence: float) -> float:
        """Map a stated confidence to the measured probability the direction is right."""
        if not self.is_calibrated(agent):
            return confidence
        if agent not in self._fits:
            history = self._outcomes[agent]
            self._fits[agent] = isotonic_fit([o.confidence for o in history], [o.correct for o in history])
        thresholds, values = self._fits[agent]
        index = bisect.bisect_right(thresholds, confidence) - 1
        return values[max(0, index)]

    def information_coefficient(self, agent: str) -> float:
        history = self._outcomes.get(agent, ())
        return _pearson([o.direction * o.confidence for o in history], [o.forward_return for o in history])

    def weight(self, agent: str) -> float:
        """0 mutes an agent with no measured skill; 1 is full weight."""
        if not self.is_calibrated(agent):
            return 1.0
        return min(1.0, max(0.0, self.information_coefficient(agent) / self.target_ic))

    def report(self, agent: str, *, bins: int = 10) -> dict[str, Any]:
        """Hit rate, Brier score and expected calibration error of the *stated* confidence."""
        history = list(self._outcomes.get(agent, ()))
        if not history:
            return {"agent": agent, "samples": 0}
        n = len(history)
        brier = sum((o.confidence - o.correct) ** 2 for o in history) / n
        ece = 0.0
        for b in range(bins):
            lo, hi = b / bins, (b + 1) / bins
            members = [o for o in history if lo <= o.confidence < hi or (b == bins - 1 and o.confidence == 1.0)]
            if members:
                gap = abs(sum(o.confidence for o in members) / len(members) - sum(o.correct for o in members) / len(members))
                ece += gap * len(members) / n
        return {
            "agent": agent,
            "samples": n,
            "hit_rate": sum(o.correct for o in history) / n,
            "brier": brier,
            "ece": ece,
            "information_coefficient": self.information_coefficient(agent),
            "weight": self.weight(agent),
            "calibrated": self.is_calibrated(agent),
        }
