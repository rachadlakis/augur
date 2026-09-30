"""Protected-entry and kill-switch behavior of the broker providers, against fake clients."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

SRC = str(Path(__file__).resolve().parents[1] / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)  # providers import `config` from src/

from providers.base import OrderRequest, OrderSide, OrderType  # noqa: E402


# --- Alpaca ---------------------------------------------------------------------------


class FakeAlpacaClient:
    def __init__(self) -> None:
        self.submitted: list = []
        self.closed_with: dict | None = None

    def submit_order(self, req):
        self.submitted.append(req)
        return {"id": "abc", "status": "accepted", "filled_qty": 0, "filled_avg_price": None}

    def close_all_positions(self, cancel_orders: bool = False):
        self.closed_with = {"cancel_orders": cancel_orders}
        return [types.SimpleNamespace(order_id="close-1", status=200)]


@pytest.fixture
def alpaca():
    from alpaca.trading.enums import OrderClass
    from providers.stocks_alpaca import AlpacaProvider

    provider = AlpacaProvider.__new__(AlpacaProvider)
    provider._client = FakeAlpacaClient()
    return provider, OrderClass


def test_alpaca_submits_bracket_when_both_exits_given(alpaca):
    provider, OrderClass = alpaca
    result = provider.place_order(OrderRequest(
        symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10,
        stop_loss=190.0, take_profit=210.0,
    ))
    req = provider._client.submitted[0]
    assert req.order_class == OrderClass.BRACKET
    assert req.stop_loss.stop_price == 190.0
    assert req.take_profit.limit_price == 210.0
    assert result.protection_status == "ATTACHED"


def test_alpaca_uses_oto_for_a_single_exit_and_rejects_protected_stop_entries(alpaca):
    provider, OrderClass = alpaca
    provider.place_order(OrderRequest(
        symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=10, stop_loss=190.0,
    ))
    assert provider._client.submitted[0].order_class == OrderClass.OTO

    rejected = provider.place_order(OrderRequest(
        symbol="AAPL", side=OrderSide.BUY, order_type=OrderType.STOP_MARKET, quantity=10,
        stop_price=201.0, stop_loss=190.0, take_profit=210.0,
    ))
    assert rejected.status == "REJECTED"
    assert len(provider._client.submitted) == 1


def test_alpaca_kill_switch_cancels_orders_and_flattens(alpaca):
    provider, _ = alpaca
    results = provider.close_all_positions()
    assert provider._client.closed_with == {"cancel_orders": True}
    assert results[0].order_id == "close-1"


# --- Binance --------------------------------------------------------------------------


class FakeBinanceError(Exception):
    pass


class FakeBinanceClient:
    def __init__(self, *, oco_fails: bool = False, flatten_fails: bool = False) -> None:
        self.orders: list[dict] = []
        self.ocos: list[dict] = []
        self.oco_fails = oco_fails
        self.flatten_fails = flatten_fails

    def get_symbol_info(self, symbol):
        return {
            "baseAsset": "BTC",
            "filters": [
                {"filterType": "LOT_SIZE", "stepSize": "0.001"},
                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
            ],
        }

    def create_order(self, **kwargs):
        if self.orders and self.flatten_fails:
            raise FakeBinanceError("flatten rejected")
        self.orders.append(kwargs)
        return {
            "orderId": len(self.orders),
            "status": "FILLED",
            "side": kwargs["side"],
            "executedQty": "0.5",
            "fills": [{"price": "100", "commission": "0.0005", "commissionAsset": "BTC"}],
        }

    def create_oco_order(self, **kwargs):
        if self.oco_fails:
            raise FakeBinanceError("oco rejected")
        self.ocos.append(kwargs)


@pytest.fixture
def binance_module(monkeypatch):
    client_mod = types.ModuleType("binance.client")
    client_mod.Client = object
    exc_mod = types.ModuleType("binance.exceptions")
    exc_mod.BinanceAPIException = FakeBinanceError
    monkeypatch.setitem(sys.modules, "binance", types.ModuleType("binance"))
    monkeypatch.setitem(sys.modules, "binance.client", client_mod)
    monkeypatch.setitem(sys.modules, "binance.exceptions", exc_mod)
    monkeypatch.delitem(sys.modules, "providers.crypto_binance", raising=False)
    return importlib.import_module("providers.crypto_binance")


def binance_provider(module, client):
    provider = module.BinanceProvider.__new__(module.BinanceProvider)
    provider._client = client
    provider._symbol_info = {}
    return provider


PROTECTED_BUY = OrderRequest(
    symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=0.5,
    stop_loss=98.0, take_profit=104.0,
)


def test_binance_attaches_oco_for_the_quantity_actually_held(binance_module):
    client = FakeBinanceClient()
    result = binance_provider(binance_module, client).place_order(PROTECTED_BUY)
    oco = client.ocos[0]
    assert oco["side"] == "SELL"
    assert oco["quantity"] == pytest.approx(0.499)  # 0.5 filled minus 0.0005 BTC commission, floored to lot
    assert oco["price"] == pytest.approx(104.0)
    assert oco["stopPrice"] == pytest.approx(98.0)
    assert oco["stopLimitPrice"] == pytest.approx(97.51)
    assert result.protection_status == "ATTACHED"


def test_binance_flattens_when_protection_cannot_attach(binance_module):
    client = FakeBinanceClient(oco_fails=True)
    result = binance_provider(binance_module, client).place_order(PROTECTED_BUY)
    assert result.protection_status == "FLATTENED"
    flatten = client.orders[1]
    assert flatten["side"] == "SELL"
    assert flatten["type"] == "MARKET"
    assert flatten["quantity"] == pytest.approx(0.499)


def test_binance_reports_unprotected_when_flatten_also_fails(binance_module):
    client = FakeBinanceClient(oco_fails=True, flatten_fails=True)
    result = binance_provider(binance_module, client).place_order(PROTECTED_BUY)
    assert result.protection_status == "UNPROTECTED"
    assert "UNPROTECTED" in (result.raw_error or "")


def test_binance_rejects_protected_non_market_entries(binance_module):
    client = FakeBinanceClient()
    result = binance_provider(binance_module, client).place_order(OrderRequest(
        symbol="BTCUSDT", side=OrderSide.BUY, order_type=OrderType.LIMIT, quantity=0.5,
        limit_price=99.0, stop_loss=98.0, take_profit=104.0,
    ))
    assert result.status == "REJECTED"
    assert client.orders == []
