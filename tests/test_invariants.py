"""Randomized invariant tests (seeded, reproducible; no extra dependencies).

Each test draws hundreds of random inputs and checks a property that must
hold for all of them, the way a property-based test would.
"""

from __future__ import annotations

import random

import pytest

from augur_agents.trading.calibration import isotonic_fit
from augur_agents.trading.evaluation import probabilistic_sharpe_ratio, walk_forward_splits
from augur_agents.trading.orchestrator import OrchestratorConsensus
from augur_agents.trading.risk import RiskManager
from augur_agents.trading.specialists import NewsSentimentAnalyst

CASES = 400
SIGNALS = ["BUY", "SELL", "HOLD", "NEUTRAL", "NO_TRADE"]
MIRROR = {"BUY": "SELL", "SELL": "BUY"}


def test_risk_never_sizes_past_budget_or_headroom():
    rng = random.Random(11)
    risk = RiskManager()
    for _ in range(CASES):
        side = rng.choice(["BUY", "SELL"])
        entry = rng.uniform(1, 1000)
        stop_dist = entry * rng.uniform(0.001, 0.2)
        target_dist = stop_dist * rng.uniform(0.5, 5)
        stop = entry - stop_dist if side == "BUY" else entry + stop_dist
        target = entry + target_dist if side == "BUY" else entry - target_dist
        if stop <= 0 or target <= 0:
            continue
        equity = rng.uniform(1000, 1e6)
        exposure = rng.uniform(0, 0.15)
        result = risk.evaluate(
            decision=side, market_snapshot=None, entry=entry, stop=stop, target=target,
            account_equity=equity, exposure=exposure, spread=0.001, liquidity=0.9, daily_loss_used=0.0,
            correlated_exposure=rng.uniform(0, 0.25),
        )
        if result["allowed"]:
            assert result["position_notional"] <= (risk.max_asset_exposure - exposure) * equity + 1e-6
            assert result["position_qty"] * stop_dist <= risk.max_risk_per_trade * equity + 1e-6
            assert target_dist / stop_dist >= risk.min_reward_risk - 1e-9
        else:
            assert result["position_notional"] == 0.0


def test_consensus_has_no_directional_bias():
    """Mirroring every BUY<->SELL must mirror the decision: no built-in long tilt."""
    rng = random.Random(12)
    consensus = OrchestratorConsensus()
    for _ in range(CASES):
        outputs = [
            {
                "agent": f"a{k}", "signal": rng.choice(SIGNALS), "confidence": rng.random(),
                "evidence_quality": rng.random(), "data_freshness": rng.random(),
                "risk_flags": rng.choice([[], [], ["crowded"]]),
            }
            for k in range(rng.randint(1, 6))
        ]
        mirrored = [{**o, "signal": MIRROR.get(o["signal"], o["signal"])} for o in outputs]
        a, b = consensus.synthesize(outputs), consensus.synthesize(mirrored)
        assert b["decision"] == MIRROR.get(a["decision"], a["decision"])
        assert b["score"] == pytest.approx(-a["score"])


def test_bracket_levels_are_mirror_images():
    rng = random.Random(13)
    for _ in range(CASES):
        entry, atr = rng.uniform(1, 1000), rng.uniform(0.01, 50)
        long = RiskManager.bracket_levels(entry=entry, atr=atr, side="BUY")
        short = RiskManager.bracket_levels(entry=entry, atr=atr, side="SELL")
        assert long["stop"] - entry == pytest.approx(entry - short["stop"])
        assert long["target"] - entry == pytest.approx(entry - short["target"])


def test_isotonic_fit_is_always_monotone():
    rng = random.Random(14)
    for _ in range(CASES // 4):
        n = rng.randint(1, 60)
        xs = [round(rng.random(), 1) for _ in range(n)]  # rounding forces ties
        ys = [float(rng.random() < 0.5) for _ in range(n)]
        thresholds, values = isotonic_fit(xs, ys)
        assert values == sorted(values)
        assert thresholds == sorted(set(thresholds))
        assert all(0.0 <= v <= 1.0 for v in values)


def test_probabilistic_sharpe_is_a_probability():
    rng = random.Random(15)
    for _ in range(CASES // 4):
        returns = [rng.gauss(rng.uniform(-0.01, 0.01), rng.uniform(0.001, 0.05)) for _ in range(rng.randint(3, 300))]
        assert 0.0 <= probabilistic_sharpe_ratio(returns) <= 1.0


def test_walk_forward_never_leaks_test_into_train():
    rng = random.Random(16)
    for _ in range(CASES // 4):
        n = rng.randint(10, 500)
        train, test, embargo = rng.randint(1, 100), rng.randint(1, 50), rng.randint(0, 10)
        for train_idx, test_idx in walk_forward_splits(n, train_size=train, test_size=test, embargo=embargo):
            assert train_idx.stop + embargo == test_idx.start
            assert test_idx.stop <= n


def test_news_sentiment_always_clamped_and_text_free():
    rng = random.Random(17)
    analyst = NewsSentimentAnalyst()
    junk = [None, "", "buy now", float("nan"), 1e9, -1e9]
    for _ in range(CASES // 4):
        events = [
            {"headline": f"h{rng.randint(0, 20)}", "source": rng.choice(["newswire", "reddit", "x"]),
             "sentiment": rng.choice(junk + [rng.uniform(-3, 3)]), "impact": rng.choice(["HIGH_IMPACT", "??", None])}
            for _ in range(rng.randint(0, 12))
        ]
        for event in analyst.canonicalize(events):
            assert -1.0 <= event["sentiment"] <= 1.0
            assert set(event) == {"source", "sentiment", "impact"}
        result = analyst.analyze(events)
        assert 0.0 <= result["confidence"] <= 0.9
