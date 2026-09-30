"""Dashboard state: accounting, exits, stop validation, kill switch. No broker is contacted."""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dash():
    spec = importlib.util.spec_from_file_location("dashboard_api_under_test", ROOT / "src" / "dashboard_api.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def state(dash, monkeypatch):
    fresh = dash.TradingState(dash.Settings(initial_capital=100000.0), connect_broker=False)
    monkeypatch.setattr(dash, "trading_state", fresh)
    return fresh


def run(coro):
    return asyncio.run(coro)


def test_realized_pnl_survives_later_price_updates(state):
    run(state.add_position("AAPL", 10, 100.0, "BUY"))
    run(state.add_position("TSLA", 5, 200.0, "BUY"))
    run(state.close_position("AAPL", 110.0))
    run(state.update_position_price("TSLA", 210.0))
    assert state.realized_pnl == pytest.approx(100.0)
    assert state.account_equity == pytest.approx(100000.0 + 100.0 + 50.0)


def test_cash_is_derived_from_positions_not_a_fixed_fraction(state):
    run(state.add_position("AAPL", 10, 100.0, "BUY"))
    run(state.add_position("XYZ", 10, 50.0, "SELL"))
    # equity 100000; longs consume 1000, short proceeds add 500
    assert state.cash() == pytest.approx(100000.0 - 1000.0 + 500.0)


def test_monitor_closes_under_one_lock_hold_without_deadlock(dash, state):
    async def scenario():
        await state.add_position("AAPL", 10, 100.0, "BUY")
        state.positions["AAPL"]["stop_price"] = 95.0
        state.positions["AAPL"]["current_price"] = 94.0
        task = asyncio.create_task(dash.monitor_positions())
        for _ in range(40):
            await asyncio.sleep(0.05)
            if "AAPL" not in state.positions:
                break
        task.cancel()
        # The lock must be free again: a deadlocked monitor would hold it forever.
        await asyncio.wait_for(state.lock.acquire(), timeout=1.0)
        state.lock.release()

    run(scenario())
    assert "AAPL" not in state.positions
    assert state.trades[-1]["thesis_status"] == "hit_stop"


def test_find_exits_handles_shorts():
    positions = {
        "S": {"side": "SELL", "current_price": 103.0, "stop_price": 102.0, "target_price": 96.0, "thesis_valid": True},
        "T": {"side": "SELL", "current_price": 95.0, "stop_price": 102.0, "target_price": 96.0, "thesis_valid": True},
    }
    from_module = importlib.import_module("dashboard_api_under_test")
    assert sorted(r for _, _, r in from_module.find_exits(positions)) == ["hit_stop", "hit_target"]


def test_stop_updates_are_validated(dash, state):
    run(state.add_position("AAPL", 10, 100.0, "BUY"))
    with pytest.raises(HTTPException):
        run(dash.update_stop("AAPL", None))  # removing the stop
    with pytest.raises(HTTPException):
        run(dash.update_stop("AAPL", 101.0))  # through the price
    run(dash.update_stop("AAPL", 97.0))
    assert state.positions["AAPL"]["stop_price"] == 97.0


def test_size_increase_respects_exposure_cap(dash, state):
    run(state.add_position("AAPL", 10, 100.0, "BUY"))
    with pytest.raises(HTTPException):
        run(dash.adjust_position_size("AAPL", 200))  # 20% of equity > 10% cap
    run(dash.adjust_position_size("AAPL", 50))
    assert state.positions["AAPL"]["quantity"] == 50


def test_manual_override_no_longer_fakes_success(dash, state):
    with pytest.raises(HTTPException) as err:
        run(dash.execute_action({"type": "MANUAL_OVERRIDE", "symbol": "AAPL", "params": {}}))
    assert err.value.status_code == 501


def test_kill_switch_halts_and_flattens(state):
    run(state.add_position("AAPL", 10, 100.0, "BUY"))
    result = run(state.kill_switch("drill"))
    assert result["closed"] == 1
    assert state.positions == {}
    assert state.halted
    assert "trading halted: drill" in state.pipeline.guard.check()


def test_alpaca_import_uses_real_prices(dash, state):
    from providers.base import AccountSnapshot, OrderSide, PositionSnapshot

    class FakeAlpaca:
        def get_account(self):
            return AccountSnapshot(equity=50200.0, cash=40000.0, buying_power=40000.0, positions={})

        def get_positions(self):
            return [
                PositionSnapshot("AAPL", 10, OrderSide.BUY, avg_entry_price=190.0, current_price=200.0),
                PositionSnapshot("TSLA", 5, OrderSide.SELL, avg_entry_price=250.0, current_price=230.0),
            ]

    state.alpaca = FakeAlpaca()
    assert run(state.load_alpaca_positions()) is True
    assert state.positions["AAPL"]["entry_price"] == 190.0
    assert state.positions["TSLA"]["side"] == "SELL"
    assert state.positions["TSLA"]["pnl"] == pytest.approx(100.0)
    assert state.account_equity == pytest.approx(50200.0)  # broker equity reproduced, not double-counted
    assert state.demo_mode is False
