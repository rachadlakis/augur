"""Market scan and FRED client, against fakes. No network."""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

from providers import fred
from providers.base import DataUnavailable

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dash():
    spec = importlib.util.spec_from_file_location("dashboard_api_scan", ROOT / "src" / "dashboard_api.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def fake_opener(values):
    def opener(url, timeout=10):
        payload = {"observations": [{"value": v} for v in values]}
        return io.BytesIO(json.dumps(payload).encode())
    return opener


def test_fred_real_yield_change_skips_missing_days():
    values = ["2.10", "."] + ["1.80"] * 30  # newest first; '.' is FRED's missing marker
    assert fred.real_yield_change_bps("key", lookback_days=20, opener=fake_opener(values)) == pytest.approx(30.0)


def test_fred_without_key_is_unavailable_not_guessed():
    with pytest.raises(DataUnavailable):
        fred.observations("DFII10", "")


class FakeData:
    def __init__(self, fail=False):
        self.fail = fail

    def hourly_and_daily(self, symbol):
        if self.fail:
            raise DataUnavailable("feed down")
        hourly = [{"open": 100.0, "high": 100.5, "low": 99.5, "close": 100.0, "volume": 1.0} for _ in range(8)]
        daily = [{"open": 96.0 + i, "high": 98.0 + i, "low": 95.0 + i, "close": 97.0 + i, "volume": 1.0} for i in range(4)]
        return hourly, daily


@pytest.fixture
def state(dash, monkeypatch):
    fresh = dash.TradingState(dash.Settings(initial_capital=100000.0), connect_broker=False)
    monkeypatch.setattr(dash, "trading_state", fresh)
    return fresh


def test_scan_instrument_reports_decision_and_reasons(dash, state):
    from augur_agents.trading.markets import BY_SYMBOL

    row = dash.scan_instrument(BY_SYMBOL["GLD"], FakeData(), real_yield_bps=-40.0)
    assert row["symbol"] == "GLD"
    assert row["decision"] in {"BUY", "SELL", "NO_TRADE"}
    assert row["reasons"] or row["order"]
    agents = {s["agent"] for s in row["specialists"]}
    assert {"technical", "macro", "term_structure"} <= agents
    assert row["change_1d_pct"] == pytest.approx((100.0 / 99.0 - 1) * 100)  # prior daily close is 99


def test_scan_instrument_reports_data_errors_instead_of_inventing_prices(dash, state):
    from augur_agents.trading.markets import BY_SYMBOL

    row = dash.scan_instrument(BY_SYMBOL["USO"], FakeData(fail=True), real_yield_bps=None)
    assert "feed down" in row["error"]
    assert "price" not in row


def test_scan_requires_alpaca(dash, monkeypatch):
    from fastapi.testclient import TestClient

    empty = dash.Settings(initial_capital=100000.0, alpaca_api_key="", alpaca_secret_key="")
    monkeypatch.setattr(dash, "trading_state", dash.TradingState(empty, connect_broker=False))
    dash._scan_cache.update(at=None, result=None)
    response = TestClient(dash.app).get("/api/markets/scan")
    assert response.status_code == 409
    assert TestClient(dash.app).get("/api/markets").json()["instruments"]
