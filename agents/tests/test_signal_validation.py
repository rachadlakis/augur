"""Forward validation of the secondary signals: store, scorer, calibrator, report. Offline."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

import pytest
from augur_agents.contracts import MarketSnapshot
from augur_agents.trading.calibration import SpecialistCalibrator
from augur_agents.trading.pipeline import TradingPipeline
from augur_agents.trading.signal_validation import (
    SignalStore,
    forward_return,
    intel_signals,
    load_calibrator,
    non_overlapping,
    price_at,
    score_pending,
    validation_report,
)

T0 = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)

RISK_OFF_NEWS = {"epu": {"percentile_1y": 0.95}, "themes": {"conflict": {"shift": -2.0}}}
USDT_ARRIVING = {
    "stablecoins": {"inflow_usd": 80e6, "outflow_usd": 5e6, "netflow_usd": 75e6, "hours": 1, "largest": [{"usd": 1e6}]},
    "eth": {"inflow_eth": 0.0, "outflow_eth": 0.0, "netflow_eth": 0.0, "largest": []},
}


def hourly_bars(start: datetime, closes: list[float]) -> list[dict]:
    return [{"timestamp": start + timedelta(hours=i), "open": c, "high": c, "low": c, "close": c, "volume": 1.0}
            for i, c in enumerate(closes)]


def whale_row(signal: str, confidence: float, target: str = "BTC/USD") -> dict:
    lean = confidence / 0.4 * (1 if signal == "BUY" else -1)
    output = {"agent": "whale_flows", "signal": signal, "confidence": confidence, "flow_score": lean}
    return {"agent": "whale_flows", "target": target, "context": "crypto", "output": output, "lean": lean}


def fill_with_outcomes(store: SignalStore, n: int, *, skill: float, seed: int = 1) -> None:
    """n whale readings 6h apart whose 6h (and 1h) returns agree with the call with probability `skill`."""
    rng = random.Random(seed)
    calls = []
    for i in range(n):
        signal = rng.choice(["BUY", "SELL"])
        confidence = rng.uniform(0.1, 0.4)
        store.record([whale_row(signal, confidence)], raw={}, at=T0 + timedelta(hours=6 * i))
        calls.append(signal)
    scores = []
    for item in store.pending(T0 + timedelta(hours=6 * n + 12)):
        direction = 1.0 if calls[item["id"] - 1] == "BUY" else -1.0
        agrees = rng.random() < skill
        scores.append({"signal_id": item["id"], "horizon_h": item["horizon_h"], "status": "scored",
                       "forward_return": direction * (1 if agrees else -1) * rng.uniform(0.001, 0.02)})
    store.add_scores(scores)


@pytest.fixture
def store(tmp_path):
    return SignalStore(tmp_path / "signals.sqlite3")


# --- What gets recorded --------------------------------------------------------------


def test_each_refresh_records_policy_for_spy_and_gold_and_whales_for_btc_and_eth(store):
    rows = intel_signals(RISK_OFF_NEWS, USDT_ARRIVING)
    by_target = {r["target"]: r for r in rows}
    assert set(by_target) == {"SPY", "GLD", "BTC/USD", "ETH/USD"}
    assert by_target["SPY"]["output"]["signal"] == "SELL" and by_target["SPY"]["lean"] < 0
    assert by_target["GLD"]["output"]["signal"] == "BUY" and by_target["GLD"]["lean"] > 0
    assert by_target["BTC/USD"]["agent"] == "whale_flows" and by_target["BTC/USD"]["lean"] > 0

    store.record(rows, raw={"news": RISK_OFF_NEWS, "whales": USDT_ARRIVING}, at=T0)
    assert store.summary()["readings"] == 1
    assert intel_signals(None, None) == []


def test_reading_an_empty_store_does_not_create_it(tmp_path):
    store = SignalStore(tmp_path / "nested" / "signals.sqlite3")
    assert store.pending(T0) == [] and store.outcomes() == []
    assert validation_report(store)["store"]["readings"] == 0
    assert not store.path.exists()


def test_signals_come_due_only_after_their_horizon(store):
    store.record(intel_signals(RISK_OFF_NEWS, USDT_ARRIVING), raw={}, at=T0)
    assert store.pending(T0 + timedelta(minutes=90)) == []
    due = store.pending(T0 + timedelta(hours=2))
    assert {(d["target"], d["horizon_h"]) for d in due} == {("BTC/USD", 1.0), ("ETH/USD", 1.0)}
    assert len(store.pending(T0 + timedelta(hours=7))) == 4
    assert len(store.pending(T0 + timedelta(hours=25))) == 6  # + policy at 24h for SPY and GLD


def test_scores_are_append_only(store):
    store.record([whale_row("BUY", 0.3)], raw={}, at=T0)
    store.add_scores([{"signal_id": 1, "horizon_h": 1.0, "status": "scored", "forward_return": 0.01}])
    store.add_scores([{"signal_id": 1, "horizon_h": 1.0, "status": "scored", "forward_return": -0.5}])
    assert [o["forward_return"] for o in store.outcomes()] == [0.01]


# --- Measuring the forward return ----------------------------------------------------


def test_price_at_uses_only_bars_that_had_finished():
    bars = hourly_bars(T0 - timedelta(hours=2), [100.0, 101.0, 102.0])  # bar starting at T0 closes at T0+1h
    assert price_at(bars, T0) == (101.0, T0)
    assert price_at(bars, T0 + timedelta(minutes=59))[0] == 101.0


def test_forward_return_and_closed_markets():
    bars = hourly_bars(T0 - timedelta(hours=1), [100.0, 100.0, 101.0, 102.0])
    assert forward_return(bars, T0, 1.0)["forward_return"] == pytest.approx(0.0)
    assert forward_return(bars, T0, 2.0)["forward_return"] == pytest.approx(0.01)
    # Nothing traded after the reading (weekend): not a 0% return, not scored at all.
    stale = hourly_bars(T0 - timedelta(hours=5), [100.0])
    assert forward_return(stale, T0, 24.0)["status"] == "skipped"
    assert forward_return(hourly_bars(T0 + timedelta(hours=1), [100.0]), T0, 1.0)["status"] == "skipped"


def test_scorer_fetches_each_asset_once_and_scores_due_signals(store):
    store.record(intel_signals(RISK_OFF_NEWS, USDT_ARRIVING), raw={}, at=T0)
    fetched = []

    def fetch(symbol, since):
        fetched.append(symbol)
        assert since <= T0 - timedelta(hours=1)
        return hourly_bars(T0 - timedelta(hours=2), [100.0 * 1.01**i for i in range(12)])

    scored = score_pending(store, fetch, now=T0 + timedelta(hours=8))
    assert sorted(fetched) == ["BTC/USD", "ETH/USD"]  # policy (24h) is not due yet
    assert len(scored) == 4
    returns = {(o["target"], o["horizon_h"]): o["forward_return"] for o in store.outcomes()}
    assert returns[("BTC/USD", 1.0)] == pytest.approx(0.01)
    assert returns[("BTC/USD", 6.0)] == pytest.approx(1.01**6 - 1)
    assert score_pending(store, fetch, now=T0 + timedelta(hours=8)) == []  # nothing scored twice


def test_a_failed_fetch_leaves_signals_pending_for_the_next_run(store):
    store.record([whale_row("BUY", 0.3)], raw={}, at=T0)

    def down(symbol, since):
        raise RuntimeError("feed down")

    assert score_pending(store, down, now=T0 + timedelta(hours=3)) == []
    assert len(store.pending(T0 + timedelta(hours=3))) == 1


def test_readings_too_old_to_score_are_written_off(store):
    store.record([whale_row("BUY", 0.3)], raw={}, at=T0)
    score_pending(store, lambda s, since: pytest.fail("should not fetch"), now=T0 + timedelta(days=40))
    assert store.pending(T0 + timedelta(days=40)) == []
    assert store.summary()["scores_by_status"] == {"skipped": 2}


# --- Overlap, calibration, report ----------------------------------------------------


def test_overlapping_readings_count_once_per_horizon():
    outcomes = [
        {"signal_id": i, "ts": (T0 + timedelta(minutes=15 * i)).isoformat(), "agent": "whale_flows",
         "target": target, "horizon_h": 6.0, "signal": "BUY", "confidence": 0.3, "lean": 0.5, "forward_return": 0.01}
        for i in range(40) for target in ("BTC/USD", "ETH/USD")
    ]  # 10 hours of 15-minute readings
    kept = non_overlapping(outcomes)
    assert len(kept) == 4  # T0 and T0+6h, for each asset


def test_calibrator_stays_neutral_until_enough_independent_samples(store):
    fill_with_outcomes(store, 20, skill=0.9)
    calibrator = load_calibrator(store)
    assert calibrator.samples("whale_flows") == 20
    assert not calibrator.is_calibrated("whale_flows")
    assert calibrator.weight("whale_flows") == 1.0 and calibrator.calibrate("whale_flows", 0.3) == 0.3


def test_skilled_signal_earns_weight_and_unskilled_one_is_muted(tmp_path):
    skilled, unskilled = SignalStore(tmp_path / "a.sqlite3"), SignalStore(tmp_path / "b.sqlite3")
    fill_with_outcomes(skilled, 80, skill=0.9)
    fill_with_outcomes(unskilled, 80, skill=0.1)
    good, bad = load_calibrator(skilled), load_calibrator(unskilled)
    assert good.is_calibrated("whale_flows") and good.weight("whale_flows") > 0.5
    assert bad.weight("whale_flows") == 0.0
    assert not good.is_calibrated("policy_news")  # no policy outcomes yet


def test_reloading_updates_the_live_calibrator_in_place_and_keeps_other_agents(store):
    live = SpecialistCalibrator()
    live.record("technical", "BUY", 0.7, 0.01)
    fill_with_outcomes(store, 60, skill=0.9)
    assert load_calibrator(store, live) is live
    assert live.samples("whale_flows") == 60 and live.samples("technical") == 1


def test_report_says_not_enough_data_below_min_samples(store):
    fill_with_outcomes(store, 10, skill=0.9)
    rows = {(r["agent"], r["horizon_h"]): r for r in validation_report(store)["signals"]}
    assert set(rows) == {("policy_news", 24.0), ("whale_flows", 1.0), ("whale_flows", 6.0)}
    whale = rows[("whale_flows", 6.0)]
    assert whale["status"] == "not_enough_data" and whale["samples"] == 10 and whale["min_samples"] == 50
    assert whale["hit_rate"] is None and whale["probabilistic_sharpe"] is None
    assert "Not enough data yet" in whale["message"]
    assert rows[("policy_news", 24.0)]["samples"] == 0


def test_report_shows_hit_rate_ic_and_significance_once_calibrated(store):
    fill_with_outcomes(store, 80, skill=0.9)
    rows = {(r["agent"], r["horizon_h"]): r for r in validation_report(store)["signals"]}
    whale = rows[("whale_flows", 6.0)]
    assert whale["status"] == "ok" and whale["samples"] == 80
    assert whale["hit_rate"] > 0.75
    assert whale["information_coefficient"] > 0 and whale["lean_ic"] > 0
    assert whale["probabilistic_sharpe"] > 0.95 and "95%" in whale["message"]
    assert whale["weight"] is not None and whale["used_by_pipeline"]
    assert rows[("whale_flows", 1.0)]["weight"] is None  # comparison horizon, not used by the pipeline

    noise = validation_report(store, min_samples=10)  # same data, threshold irrelevant to the verdict
    assert noise["signals"][1]["status"] == "ok"


def test_report_flags_a_coin_flip_as_luck(store):
    fill_with_outcomes(store, 80, skill=0.5, seed=7)
    whale = next(r for r in validation_report(store)["signals"] if r["horizon_h"] == 6.0)
    assert whale["probabilistic_sharpe"] < 0.95 and "luck" in whale["message"]


# --- Calibrated secondary signals still can't originate a trade ----------------------


def test_perfectly_calibrated_secondary_signals_cannot_trade_a_flat_market(tmp_path):
    store = SignalStore(tmp_path / "s.sqlite3")
    fill_with_outcomes(store, 80, skill=1.0)
    calibrator = load_calibrator(store)
    calibrator.load("policy_news", [("BUY", 0.5, 0.01 * (i + 1)) for i in range(60)] + [("SELL", 0.1, -0.001)] * 10)
    assert calibrator.weight("whale_flows") == 1.0 and calibrator.weight("policy_news") > 0

    flat = {"open": 100.0, "high": 100.1, "low": 99.9, "close": 100.0, "volume": 1.0}
    snapshot = MarketSnapshot(asset="BTC/USD", timestamp=T0, price=100.0, ohlcv={"1h": flat, "4h": flat, "1d": flat},
                              volume=1.0, spread=0.0005, liquidity=0.9, volatility={"atr": 1.0})
    bullish_policy = {"epu": {"percentile_1y": 0.0}, "themes": {"rates": {"shift": 5.0}}}
    result = TradingPipeline(calibrator=calibrator).evaluate(
        market_snapshot=snapshot, account_equity=100_000.0, exposure=0.0, daily_loss_used=0.0, spread=0.0005,
        expected_slippage=0.0005, liquidity=0.9, macro_metrics={"dxy": 100.0, "fed_message": "neutral"}, now=T0,
        policy_context=bullish_policy, whale_flows=USDT_ARRIVING,
    )
    assert result["specialists"]["whales"]["signal"] == "BUY"
    assert result["specialists"]["policy"]["signal"] == "BUY"
    assert result["order"] is None
