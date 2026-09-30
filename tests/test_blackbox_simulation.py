"""Black-box test: drive the whole decision stack through simulated markets.

Nothing here reaches into internals. Random-walk price paths go in as market
snapshots; orders come out and are resolved against the bars that follow. The
assertions are the safety contract any market must respect, whatever the
strategy's P&L turns out to be.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone

import pytest

from augur_agents.contracts import MarketSnapshot
from augur_agents.trading.backtest import PaperTradingBacktester, simulate_bracket_exit
from augur_agents.trading.calibration import SpecialistCalibrator
from augur_agents.trading.pipeline import TradingPipeline

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
HOURS = 24 * 20


def price_path(seed: int, drift: float, vol: float) -> list[dict[str, float]]:
    rng = random.Random(seed)
    price = 100.0
    bars = []
    for _ in range(HOURS):
        open_ = price
        close = open_ * math.exp(drift + vol * rng.gauss(0, 1))
        high = max(open_, close) * (1 + abs(rng.gauss(0, vol / 2)))
        low = min(open_, close) * (1 - abs(rng.gauss(0, vol / 2)))
        bars.append({"open": open_, "high": high, "low": low, "close": close})
        price = close
    return bars


def snapshot_at(bars: list[dict[str, float]], i: int) -> MarketSnapshot:
    def window(n: int) -> dict[str, float]:
        chunk = bars[max(0, i - n + 1): i + 1]
        return {
            "open": chunk[0]["open"], "high": max(b["high"] for b in chunk),
            "low": min(b["low"] for b in chunk), "close": chunk[-1]["close"], "volume": 1.0,
        }

    recent = bars[max(0, i - 13): i + 1]
    atr = sum(b["high"] - b["low"] for b in recent) / len(recent)
    return MarketSnapshot(
        asset="SIM", timestamp=START + timedelta(hours=i), price=bars[i]["close"],
        ohlcv={"1h": window(1), "4h": window(4), "1d": window(24)},
        volume=1.0, spread=0.0005, liquidity=0.9, volatility={"atr": atr},
    )


MARKETS = [
    pytest.param(1, 0.0008, 0.006, id="bull"),
    pytest.param(2, -0.0008, 0.006, id="bear"),
    pytest.param(3, 0.0, 0.004, id="chop"),
    pytest.param(4, 0.0, 0.02, id="crash-vol"),
]


@pytest.mark.parametrize("seed,drift,vol", MARKETS)
def test_safety_contract_holds_in_every_market(seed, drift, vol):
    bars = price_path(seed, drift, vol)
    calibrator = SpecialistCalibrator(min_samples=30)
    pipeline = TradingPipeline(calibrator=calibrator)
    backtester = PaperTradingBacktester(10000.0, fee_bps=10.0)
    macro = {"dxy": 100.0, "fed_message": "neutral", "horizon_hours": 24}
    entries_by_day: dict[str, int] = {}

    i = 24
    while i < HOURS - 25:
        now = START + timedelta(hours=i)
        equity = backtester.capital
        result = pipeline.evaluate(
            market_snapshot=snapshot_at(bars, i), account_equity=equity, exposure=0.0, daily_loss_used=0.0,
            spread=0.0005, expected_slippage=0.0005, liquidity=0.9, macro_metrics=macro, now=now,
        )
        forward = bars[i + 24]["close"] / bars[i]["close"] - 1.0
        pipeline.record_outcome(result, forward)

        order = result["order"]
        if order is None:
            assert result["decision"] == "NO_TRADE"
            i += 1
            continue

        # 1. Every entry is bracketed, on the correct sides.
        entry, stop, target = order["entry"], order["stop_loss"], order["take_profit"]
        if order["side"] == "BUY":
            assert stop < entry < target
        else:
            assert target < entry < stop
        # 2. Notional never exceeds the per-asset exposure cap.
        assert order["notional"] <= 0.10 * equity + 1e-6
        # 3. Loss at the stop never exceeds the per-trade risk budget.
        assert abs(entry - stop) * order["quantity"] <= 0.005 * equity + 1e-6
        # 4. The daily entry cap holds.
        day = now.date().isoformat()
        entries_by_day[day] = entries_by_day.get(day, 0) + 1
        assert entries_by_day[day] <= pipeline.guard.max_entries_per_day

        side = "LONG" if order["side"] == "BUY" else "SHORT"
        exit_price, reason, used = simulate_bracket_exit(side=side, stop=stop, target=target, bars=bars[i + 1: i + 25])
        trade = backtester.execute_trade(
            {"entry": entry, "size": order["quantity"], "side": side}, exit_price, slippage_bps=5.0,
            exit_time=now + timedelta(hours=used + 1),
        )
        # 5. Without a gap, a stopped trade loses at most its budget plus costs.
        if reason == "stop":
            costs = trade.fee_cost + trade.slippage_cost
            assert -trade.pnl <= 0.005 * equity + costs + 1e-6
        i += used + 1

    metrics = backtester.get_metrics()
    assert math.isfinite(metrics["total_pnl"])
    # 6. Hard floor: capital can't be destroyed with 0.5% risk per trade in 20 days.
    assert backtester.capital > 10000.0 * 0.80
