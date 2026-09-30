"""Smoke tests: does everything start and answer, exactly as a user would run it?

Covers the dashboard's HTTP surface through FastAPI's TestClient (startup
tasks are not run, so no broker is contacted) and the demo script as a real
subprocess.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dash():
    spec = importlib.util.spec_from_file_location("dashboard_api_smoke", ROOT / "src" / "dashboard_api.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def client(dash, monkeypatch):
    state = dash.TradingState(dash.Settings(initial_capital=100000.0), connect_broker=False)
    monkeypatch.setattr(dash, "trading_state", state)
    return TestClient(dash.app)


def test_health_reports_mode_and_halt(client):
    body = client.get("/api/health").json()
    assert body["status"] == "healthy"
    assert body["mode"] == "demo"
    assert body["halted"] is False


def test_portfolio_shape(client):
    body = client.get("/api/portfolio").json()
    for key in ("account_equity", "cash", "buying_power", "total_pnl", "max_drawdown", "positions", "recent_trades"):
        assert key in body
    assert body["cash"] == body["account_equity"]  # no positions: all cash, not a made-up 30%


def test_positions_trades_indicators_endpoints_answer(client):
    assert client.get("/api/positions").json() == []
    assert client.get("/api/trades").json() == []
    assert client.get("/api/indicators").json() == {"indicators": []}


def test_command_parsing(client):
    body = client.post("/api/command", json={"text": "show portfolio summary"}).json()
    assert body["understood"] is True
    assert body["action"] == "SHOW_SUMMARY"


def test_kill_switch_round_trip(client):
    assert client.post("/api/kill-switch", json={"reason": "smoke"}).json()["halted"] is True
    health = client.get("/api/health").json()
    assert health["halted"] is True
    assert health["halt_reason"] == "smoke"
    client.post("/api/resume")
    assert client.get("/api/health").json()["halted"] is False


def test_manual_override_is_refused(client):
    response = client.post("/api/action", json={"type": "MANUAL_OVERRIDE", "symbol": "AAPL"})
    assert response.status_code == 501


def test_cors_allows_local_dev_server_only(client):
    ok = client.options(
        "/api/portfolio",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    blocked = client.options(
        "/api/portfolio",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"},
    )
    assert blocked.headers.get("access-control-allow-origin") is None


def test_integrations_status_never_leaks_secrets(client, dash):
    body = client.get("/api/integrations").json()
    names = {item["id"] for item in body["integrations"]}
    assert {"alpaca", "binance"} <= names
    raw = str(body)
    for field in ("alpaca_api_key", "alpaca_secret_key", "binance_api_key", "binance_api_secret"):
        secret = getattr(dash.trading_state.settings, field).get_secret_value()
        if secret:
            assert secret not in raw


def test_demo_script_runs_end_to_end():
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "demo_trading_system.py")],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=120,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "ALL PHASES COMPLETE" in result.stdout


def test_setup_wizard_status_runs_and_hides_keys():
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "setup_integrations.py"), "--status"],
        capture_output=True, text=True, encoding="utf-8", env=env, timeout=60,
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert "Connections:" in result.stdout
    assert "Practice mode stays ON" in result.stdout
    from config import Settings

    settings = Settings()
    for field in ("alpaca_api_key", "alpaca_secret_key", "binance_api_key", "binance_api_secret"):
        secret = getattr(settings, field).get_secret_value()
        if secret:
            assert secret not in result.stdout


def test_write_env_merges_without_touching_other_lines(tmp_path):
    sys.path.insert(0, str(ROOT / "src"))
    import integrations

    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nALPACA_PAPER=true\nNEWSAPI_KEY=old\n", encoding="utf-8")
    integrations.write_env({"NEWSAPI_KEY": "new", "FRED_API_KEY": "abc"}, env_file)
    assert env_file.read_text(encoding="utf-8") == "# comment\nALPACA_PAPER=true\nNEWSAPI_KEY=new\nFRED_API_KEY=abc\n"
