"""Order routing, broker reconciliation, crypto protection and watch-only wallets. All fakes."""

from __future__ import annotations

import asyncio
import importlib.util
import io
import json
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from providers import wallets
from providers.base import AccountSnapshot, DataUnavailable, OrderResult, OrderSide, PositionSnapshot

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def dash():
    spec = importlib.util.spec_from_file_location("dashboard_api_orders", ROOT / "src" / "dashboard_api.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeBroker:
    """Stands in for AlpacaProvider: records orders, holds a position book."""

    def __init__(self):
        self.orders = []
        self.book: dict[str, PositionSnapshot] = {}
        self.fills = {}

    def get_account(self):
        return AccountSnapshot(equity=100000.0, cash=100000.0, buying_power=100000.0, positions={})

    def get_positions(self):
        return list(self.book.values())

    def place_order(self, order):
        self.orders.append(order)
        self.book[order.symbol] = PositionSnapshot(order.symbol, order.quantity, order.side, 100.0, 100.0)
        protection = "STOP_ATTACHED" if "/" in order.symbol else "ATTACHED"
        return OrderResult("o-1", "filled", order.quantity, 100.0, protection_status=protection)

    def last_fill_price(self, symbol):
        return self.fills[symbol]

    def close_position(self, symbol):
        self.book.pop(symbol, None)
        return OrderResult("c-1", "filled", 0.0, None)


class FakePrices:
    def __init__(self, prices):
        self.prices = prices

    def latest_prices(self, symbols):
        return {s: self.prices[s] for s in symbols if s in self.prices}


@pytest.fixture
def state(dash, monkeypatch):
    fresh = dash.TradingState(dash.Settings(initial_capital=100000.0, alpaca_paper=True), connect_broker=False)
    fresh.alpaca = FakeBroker()
    fresh.market_data = FakePrices({"GLD": 100.0, "BTC/USD": 100.0, "USO": 100.0})
    assert asyncio.run(fresh.load_alpaca_positions()) is True
    monkeypatch.setattr(dash, "trading_state", fresh)
    return fresh


@pytest.fixture
def client(dash, state):
    return TestClient(dash.app)


TICKET = {"symbol": "GLD", "side": "BUY", "quantity": 1000, "stop_loss": 98.0, "take_profit": 104.0}


def test_empty_broker_book_is_adopted_not_replaced_by_demo_data(state):
    assert state.mode == "paper"
    assert state.positions == {}


def test_order_is_resized_by_server_and_bracketed(client, state):
    body = client.post("/api/orders", json=TICKET).json()
    order = state.alpaca.orders[0]
    # risk: 100000 * 0.5% / 2% stop = 25000 notional, capped at 10% asset exposure = 10000 → 100 shares
    assert order.quantity == 100
    assert (order.stop_loss, order.take_profit) == (98.0, 104.0)
    assert body["protection"] == "ATTACHED"
    assert state.positions["GLD"]["local_stop"] is False  # exits belong to the broker


def test_whole_shares_and_risk_refusals(client, state):
    bad_rr = {**TICKET, "take_profit": 101.0}
    response = client.post("/api/orders", json=bad_rr)
    assert response.status_code == 400
    assert "reward/risk" in response.json()["detail"]
    tiny = client.post("/api/orders", json={**TICKET, "quantity": 0.4})
    assert tiny.status_code == 400
    assert "whole share" in tiny.json()["detail"]
    assert state.alpaca.orders == []


def test_crypto_short_refused_and_crypto_target_enforced_locally(client, state):
    assert client.post("/api/orders", json={**TICKET, "symbol": "BTC/USD", "side": "SELL", "stop_loss": 102.0, "take_profit": 96.0}).status_code == 400
    ok = client.post("/api/orders", json={**TICKET, "symbol": "BTC/USD", "quantity": 0.5}).json()
    assert ok["protection"] == "STOP_ATTACHED"
    assert state.positions["BTC/USD"]["local_target"] is True


def test_real_money_needs_typed_phrase(client, state, dash):
    state.settings = dash.Settings(initial_capital=100000.0, alpaca_paper=False)
    assert state.mode == "live"
    refused = client.post("/api/orders", json=TICKET)
    assert refused.status_code == 403
    assert client.post("/api/orders", json={**TICKET, "confirm_real_money": "REAL MONEY"}).status_code == 200


def test_kill_switch_blocks_orders(client, state):
    state.pipeline.guard.halt("drill")
    response = client.post("/api/orders", json=TICKET)
    assert response.status_code == 409
    assert "drill" in response.json()["detail"]


def test_unknown_symbol_and_demo_mode_refused(client, state, dash):
    assert client.post("/api/orders", json={**TICKET, "symbol": "DOGE"}).status_code == 400
    state.demo_mode = True
    assert client.post("/api/orders", json=TICKET).status_code == 409


def test_broker_exit_is_recorded_at_the_real_fill(client, state):
    client.post("/api/orders", json=TICKET)
    state.alpaca.book.pop("GLD")  # the bracket's target filled at the broker
    state.alpaca.fills["GLD"] = 104.0
    assert asyncio.run(state.sync_broker()) == ["GLD"]
    trade = state.trades[-1]
    assert trade["exit_price"] == 104.0
    assert trade["thesis_status"] == "closed_at_broker"
    assert trade["pnl"] == pytest.approx((104.0 - 100.0) * 100)


def test_monitor_leaves_broker_exits_to_the_broker(dash):
    positions = {"GLD": {"side": "BUY", "current_price": 90.0, "stop_price": 98.0, "target_price": 104.0,
                         "local_stop": False, "local_target": False, "thesis_valid": True}}
    assert dash.find_exits(positions) == []
    positions["GLD"]["local_stop"] = True
    assert dash.find_exits(positions)[0][2] == "hit_stop"


# --- Alpaca crypto protection ----------------------------------------------------------


class FakeCryptoClient:
    def __init__(self, stop_fails=False):
        self.submitted = []
        self.stop_fails = stop_fails
        self.closed = []

    def submit_order(self, req):
        if type(req).__name__ == "StopLimitOrderRequest" and self.stop_fails:
            from alpaca.common.exceptions import APIError
            raise APIError("stop rejected")
        self.submitted.append(req)
        return {"id": f"id-{len(self.submitted)}", "status": "accepted", "filled_qty": "0", "filled_avg_price": None}

    def get_order_by_id(self, order_id):
        return {"id": order_id, "status": "filled", "filled_qty": "0.5", "filled_avg_price": "100"}

    def get_orders(self, filter=None):
        return []

    def close_position(self, symbol):
        self.closed.append(symbol)
        return {"id": "flat", "status": "accepted", "filled_qty": "0", "filled_avg_price": None}


@pytest.fixture
def alpaca_provider():
    from providers.stocks_alpaca import AlpacaProvider

    provider = AlpacaProvider.__new__(AlpacaProvider)
    return provider


def crypto_ticket():
    from providers.base import OrderRequest, OrderType

    return OrderRequest("BTC/USD", OrderSide.BUY, OrderType.MARKET, 0.5, stop_loss=98.0, take_profit=104.0)


def test_alpaca_crypto_entry_attaches_gtc_stop_limit(alpaca_provider):
    from alpaca.trading.enums import TimeInForce

    alpaca_provider._client = FakeCryptoClient()
    result = alpaca_provider.place_order(crypto_ticket())
    entry, stop = alpaca_provider._client.submitted
    assert entry.time_in_force == TimeInForce.GTC
    assert stop.stop_price == 98.0 and stop.limit_price == pytest.approx(97.51)
    assert stop.qty == 0.5
    assert result.protection_status == "STOP_ATTACHED"


def test_alpaca_crypto_flattens_when_stop_fails(alpaca_provider):
    alpaca_provider._client = FakeCryptoClient(stop_fails=True)
    result = alpaca_provider.place_order(crypto_ticket())
    assert alpaca_provider._client.closed == ["BTC/USD"]
    assert result.protection_status == "FLATTENED"


def test_alpaca_bracket_refuses_fractional_shares(alpaca_provider):
    from providers.base import OrderRequest, OrderType

    alpaca_provider._client = FakeCryptoClient()
    result = alpaca_provider.place_order(OrderRequest("GLD", OrderSide.BUY, OrderType.MARKET, 1.5, stop_loss=98.0, take_profit=104.0))
    assert result.status == "REJECTED"
    assert "whole shares" in (result.raw_error or "")


# --- watch-only wallets ------------------------------------------------------------------

ADDRESS = "0x" + "ab" * 20


def test_wallet_rejects_private_keys_loudly():
    with pytest.raises(ValueError, match="PRIVATE KEY"):
        wallets.validate_address("0x" + "1f" * 32)
    with pytest.raises(ValueError):
        wallets.validate_address("hello")
    assert wallets.validate_address(f"  {ADDRESS} ") == ADDRESS


def test_wallet_balance_from_rpc():
    def opener(request, timeout=10):
        body = json.loads(request.data)
        assert body["method"] == "eth_getBalance" and body["params"] == [ADDRESS, "latest"]
        return io.BytesIO(json.dumps({"result": hex(3 * 10**18 // 2)}).encode())

    assert wallets.eth_balance(ADDRESS, opener=opener) == pytest.approx(1.5)


def test_wallet_rpc_error_is_unavailable():
    def opener(request, timeout=10):
        return io.BytesIO(json.dumps({"error": {"message": "nope"}}).encode())

    with pytest.raises(DataUnavailable):
        wallets.eth_balance(ADDRESS, opener=opener)


def test_wallet_endpoint_refuses_private_key(client):
    response = client.post("/api/wallets", json={"address": "0x" + "1f" * 32})
    assert response.status_code == 400
    assert "PRIVATE KEY" in response.json()["detail"]
