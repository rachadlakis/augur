"""Dashboard wiring of signal forward-validation: record on refresh, score, report. No network."""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from augur_agents.trading import signal_validation
from augur_agents.trading.calibration import SpecialistCalibrator
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]

NEWS = {"epu": {"percentile_1y": 0.95}, "themes": {"conflict": {"shift": -2.0}}}
FLOWS = {
    "stablecoins": {"inflow_usd": 80e6, "outflow_usd": 5e6, "netflow_usd": 75e6, "hours": 1, "largest": [{"usd": 1e6}]},
    "eth": {"inflow_eth": 0.0, "outflow_eth": 0.0, "netflow_eth": 0.0, "largest": []},
}


@pytest.fixture
def dash(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("dashboard_api_validation", ROOT / "src" / "dashboard_api.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "trading_state", module.TradingState(module.Settings(), connect_broker=False))
    monkeypatch.setattr(module, "signal_store", signal_validation.SignalStore(tmp_path / "signals.sqlite3"))
    monkeypatch.setattr(module.news_feeds, "macro_news_context", lambda key: NEWS)
    monkeypatch.setattr(module.whales, "whale_flow_snapshot", lambda **kw: FLOWS)
    return module


def test_store_defaults_to_the_data_dir_which_tests_redirect(dash):
    assert dash.DATA_DIR != ROOT / "data"


def test_every_intel_refresh_is_recorded(dash):
    client = TestClient(dash.app)
    client.get("/api/intel?refresh=true")
    client.get("/api/intel?refresh=true")
    summary = dash.signal_store.summary()
    assert summary["readings"] == 2
    targets = {row["target"] for row in dash.signal_store.pending(datetime.now(timezone.utc) + timedelta(days=2))}
    assert targets == {"SPY", "GLD", "BTC/USD", "ETH/USD"}


def test_a_broken_store_does_not_break_the_intel_feed(dash, monkeypatch):
    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(dash.signal_store, "record", broken)
    body = TestClient(dash.app).get("/api/intel?refresh=true").json()
    assert body["readings"]["whales_for_btc"]["signal"] == "BUY"


def test_validation_endpoint_reports_not_enough_data_at_first(dash):
    body = TestClient(dash.app).get("/api/intel/validation").json()
    assert {row["status"] for row in body["signals"]} == {"not_enough_data"}
    assert {(row["agent"], row["horizon_h"]) for row in body["signals"]} == {
        ("policy_news", 24.0), ("whale_flows", 1.0), ("whale_flows", 6.0)}


def test_scoring_needs_alpaca_and_then_feeds_the_shared_calibrator(dash, monkeypatch):
    calibrator = SpecialistCalibrator(min_samples=1)
    monkeypatch.setattr(dash, "signal_calibrator", calibrator)
    start = datetime.now(timezone.utc) - timedelta(hours=8)
    dash.signal_store.record(signal_validation.intel_signals(NEWS, FLOWS), raw={}, at=start)

    monkeypatch.setattr(dash, "_integration_configured", lambda integration_id: False)
    assert dash.score_intel_signals() == 0

    class FakeMarketData:
        def __init__(self, settings):
            pass

        def bars(self, symbol, timeframe, lookback):
            first = datetime.now(timezone.utc) - lookback
            return [{"timestamp": first + timedelta(hours=i), "close": 100.0 + i} for i in range(int(lookback.total_seconds() // 3600))]

    monkeypatch.setattr(dash, "_integration_configured", lambda integration_id: True)
    monkeypatch.setattr(dash, "AlpacaMarketData", FakeMarketData)
    assert dash.score_intel_signals() == 4  # BTC and ETH at 1h and 6h; policy waits for 24h
    assert calibrator.samples("whale_flows") == 2  # the 6h outcomes for BTC and ETH
    assert calibrator.weight("whale_flows") >= 0


def test_dashboard_pipelines_share_the_signal_calibrator(dash):
    assert dash.TradingState(dash.Settings(), connect_broker=False).pipeline.calibrator is dash.signal_calibrator
