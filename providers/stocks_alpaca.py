"""
Alpaca implementation of ExecutionProvider.
Requires: pip install alpaca-py
"""

import math
import time
from typing import Any

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import (
    MarketOrderRequest, LimitOrderRequest, StopOrderRequest, StopLimitOrderRequest,
    StopLossRequest, TakeProfitRequest, GetOrdersRequest,
)
from alpaca.trading.enums import OrderClass, OrderSide as AlpacaSide, QueryOrderStatus, TimeInForce
from alpaca.data.enums import DataFeed
from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import CryptoLatestTradeRequest, StockLatestTradeRequest
from alpaca.common.exceptions import APIError

from config import Settings
from providers.base import (
    ExecutionProvider, OrderRequest, OrderResult, OrderSide, OrderType,
    AccountSnapshot, DataUnavailable, PositionSnapshot,
)


def _field(obj: Any, name: str) -> Any:
    """Read a field from either an SDK model or its raw-dict form."""
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def _float(value: Any) -> float | None:
    return float(value) if value not in (None, "") else None


def _order_result(resp: Any, *, protection_status: str | None = None) -> OrderResult:
    return OrderResult(
        order_id=str(_field(resp, "id") or ""),
        status=str(_field(resp, "status") or ""),
        filled_qty=_float(_field(resp, "filled_qty")) or 0.0,
        avg_fill_price=_float(_field(resp, "filled_avg_price")),
        protection_status=protection_status,
    )


# How far past the stop trigger the crypto stop-limit may fill (Alpaca crypto has no stop-market).
CRYPTO_STOP_LIMIT_BUFFER = 0.005
FILL_WAIT_SECONDS = 5.0


def is_crypto(symbol: str) -> bool:
    return "/" in symbol


def _rejected(error: Exception | str) -> OrderResult:
    return OrderResult(order_id="", status="REJECTED", filled_qty=0.0, avg_fill_price=None, raw_error=str(error))


class AlpacaProvider(ExecutionProvider):
    def __init__(self, settings: Settings):
        api_key = settings.alpaca_api_key.get_secret_value()
        secret_key = settings.alpaca_secret_key.get_secret_value()
        self._client = TradingClient(api_key=api_key, secret_key=secret_key, paper=settings.alpaca_paper)
        self._data = StockHistoricalDataClient(api_key=api_key, secret_key=secret_key)
        self._crypto_data = CryptoHistoricalDataClient(api_key=api_key, secret_key=secret_key)

    def get_account(self) -> AccountSnapshot:
        try:
            acct = self._client.get_account()
            positions = self._client.get_all_positions()
        except APIError as e:
            raise DataUnavailable(f"Alpaca account fetch failed: {e}") from e

        position_dict = {}
        for p in positions:
            symbol, qty = _field(p, "symbol"), _field(p, "qty")
            if symbol and qty is not None:
                position_dict[symbol] = float(qty)

        return AccountSnapshot(
            equity=_float(_field(acct, "equity")) or 0.0,
            cash=_float(_field(acct, "cash")) or 0.0,
            buying_power=_float(_field(acct, "buying_power")) or 0.0,
            positions=position_dict,
        )

    def get_positions(self) -> list[PositionSnapshot]:
        try:
            positions = self._client.get_all_positions()
        except APIError as e:
            raise DataUnavailable(f"Alpaca positions fetch failed: {e}") from e

        snapshots = []
        for p in positions:
            qty = _float(_field(p, "qty")) or 0.0
            side = str(getattr(_field(p, "side"), "value", _field(p, "side")) or "").lower()
            is_short = side == "short" or qty < 0
            snapshots.append(PositionSnapshot(
                symbol=str(_field(p, "symbol")),
                quantity=abs(qty),
                side=OrderSide.SELL if is_short else OrderSide.BUY,
                avg_entry_price=_float(_field(p, "avg_entry_price")),
                current_price=_float(_field(p, "current_price")),
            ))
        return snapshots

    def place_order(self, order: OrderRequest) -> OrderResult:
        side = AlpacaSide.BUY if order.side.value == "BUY" else AlpacaSide.SELL
        crypto = is_crypto(order.symbol)
        # Alpaca crypto accepts GTC/IOC only; equities use DAY.
        tif = TimeInForce.GTC if crypto else TimeInForce.DAY

        if crypto and order.has_protection:
            return self._protected_crypto_entry(order)

        # Protection rides on the entry as one broker-side order (bracket, or OTO
        # with a single exit), so a fill can never exist without its stop.
        protection: dict = {}
        if order.has_protection:
            if order.order_type not in (OrderType.MARKET, OrderType.LIMIT):
                return _rejected("protected entries must be MARKET or LIMIT orders")
            if order.quantity != math.floor(order.quantity):
                return _rejected("Alpaca brackets need whole shares; round the quantity down")
            both = order.stop_loss is not None and order.take_profit is not None
            protection["order_class"] = OrderClass.BRACKET if both else OrderClass.OTO
            if order.stop_loss is not None:
                protection["stop_loss"] = StopLossRequest(stop_price=float(order.stop_loss))
            if order.take_profit is not None:
                protection["take_profit"] = TakeProfitRequest(limit_price=float(order.take_profit))

        try:
            req: MarketOrderRequest | LimitOrderRequest | StopOrderRequest
            if order.order_type == OrderType.MARKET:
                req = MarketOrderRequest(
                    symbol=order.symbol, qty=order.quantity,
                    side=side, time_in_force=tif, **protection,
                )
            elif order.order_type == OrderType.LIMIT:
                limit_price = float(order.limit_price) if order.limit_price is not None else 0.0
                req = LimitOrderRequest(
                    symbol=order.symbol, qty=order.quantity, side=side,
                    time_in_force=tif, limit_price=limit_price, **protection,
                )
            else:  # STOP_MARKET / STOP_LIMIT
                stop_price = float(order.stop_price) if order.stop_price is not None else 0.0
                req = StopOrderRequest(
                    symbol=order.symbol, qty=order.quantity, side=side,
                    time_in_force=tif, stop_price=stop_price,
                )
            resp = self._client.submit_order(req)
        except APIError as e:
            return _rejected(e)

        return _order_result(resp, protection_status="ATTACHED" if order.has_protection else None)

    def _wait_for_fill(self, order_id: str) -> Any:
        deadline = time.monotonic() + FILL_WAIT_SECONDS
        while True:
            current = self._client.get_order_by_id(order_id)
            status = str(getattr(_field(current, "status"), "value", _field(current, "status")) or "").lower()
            if status in {"filled", "canceled", "cancelled", "expired", "rejected"} or time.monotonic() > deadline:
                return current
            time.sleep(0.25)

    def _protected_crypto_entry(self, order: OrderRequest) -> OrderResult:
        """Alpaca crypto has no brackets: fill the entry, then attach a stop-limit at once.

        If the stop cannot be attached the fill is closed immediately, so a
        position never sits unprotected. The take-profit is not sent (crypto
        has no OCO here); the position monitor enforces it.
        """
        if order.order_type != OrderType.MARKET or order.stop_loss is None:
            return _rejected("protected crypto entries must be MARKET orders with a stop_loss")
        side = AlpacaSide.BUY if order.side.value == "BUY" else AlpacaSide.SELL
        exit_side = AlpacaSide.SELL if side == AlpacaSide.BUY else AlpacaSide.BUY
        try:
            entry = self._client.submit_order(MarketOrderRequest(
                symbol=order.symbol, qty=order.quantity, side=side, time_in_force=TimeInForce.GTC,
            ))
            filled = self._wait_for_fill(str(_field(entry, "id")))
        except APIError as e:
            return _rejected(e)

        result = _order_result(filled)
        if result.filled_qty <= 0:
            return OrderResult(
                order_id=result.order_id, status=result.status, filled_qty=0.0, avg_fill_price=None,
                raw_error="entry did not fill in time; nothing to protect", protection_status=None,
            )

        stop = float(order.stop_loss)
        buffer = 1 - CRYPTO_STOP_LIMIT_BUFFER if exit_side == AlpacaSide.SELL else 1 + CRYPTO_STOP_LIMIT_BUFFER
        try:
            self._client.submit_order(StopLimitOrderRequest(
                symbol=order.symbol, qty=result.filled_qty, side=exit_side, time_in_force=TimeInForce.GTC,
                stop_price=round(stop, 2), limit_price=round(stop * buffer, 2),
            ))
            return OrderResult(
                order_id=result.order_id, status=result.status, filled_qty=result.filled_qty,
                avg_fill_price=result.avg_fill_price, protection_status="STOP_ATTACHED",
            )
        except APIError as e:
            flatten = self.close_position(order.symbol)
            status = "FLATTENED" if flatten.status != "REJECTED" else "UNPROTECTED"
            return OrderResult(
                order_id=result.order_id, status=result.status, filled_qty=result.filled_qty,
                avg_fill_price=result.avg_fill_price, protection_status=status,
                raw_error=f"stop could not be attached ({e}); position {status.lower()}",
            )

    def last_fill_price(self, symbol: str) -> float:
        """Average price of the most recent filled order for `symbol` (e.g. a bracket exit)."""
        try:
            orders = self._client.get_orders(GetOrdersRequest(
                status=QueryOrderStatus.CLOSED, symbols=[symbol], limit=20, nested=True,
            ))
        except APIError as e:
            raise DataUnavailable(f"Alpaca order history unavailable for {symbol}: {e}") from e
        candidates = []
        for o in orders:
            candidates.append(o)
            candidates.extend(_field(o, "legs") or [])  # bracket exits are legs of the entry
        filled = [o for o in candidates if _float(_field(o, "filled_avg_price")) and _field(o, "filled_at")]
        if not filled:
            raise DataUnavailable(f"no filled orders for {symbol}")
        latest = max(filled, key=lambda o: str(_field(o, "filled_at")))
        return float(_float(_field(latest, "filled_avg_price")) or 0.0)

    def close_position(self, symbol: str) -> OrderResult:
        # Bracket legs hold the shares, so a plain close is rejected until they are cancelled.
        try:
            open_orders = self._client.get_orders(GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[symbol]))
            for open_order in open_orders:
                self._client.cancel_order_by_id(_field(open_order, "id"))
            resp = self._client.close_position(symbol)
        except APIError as e:
            return _rejected(e)
        return _order_result(resp)

    def close_all_positions(self) -> list[OrderResult]:
        try:
            responses = self._client.close_all_positions(cancel_orders=True)
        except APIError as e:
            return [_rejected(e)]
        return [
            OrderResult(
                order_id=str(_field(r, "order_id") or ""),
                status=str(_field(r, "status") or ""),
                filled_qty=0.0,
                avg_fill_price=None,
            )
            for r in responses
        ]

    def cancel_order(self, order_id: str) -> bool:
        try:
            self._client.cancel_order_by_id(order_id)
            return True
        except APIError:
            return False

    def get_last_price(self, symbol: str) -> float:
        try:
            if is_crypto(symbol):
                trades = self._crypto_data.get_crypto_latest_trade(CryptoLatestTradeRequest(symbol_or_symbols=symbol))
            else:
                trades = self._data.get_stock_latest_trade(
                    StockLatestTradeRequest(symbol_or_symbols=symbol, feed=DataFeed.IEX)
                )
        except APIError as e:
            raise DataUnavailable(f"Alpaca latest trade fetch failed for {symbol}: {e}") from e
        trade = trades.get(symbol) if isinstance(trades, dict) else None
        price = _float(_field(trade, "price")) if trade is not None else None
        if not price:
            raise DataUnavailable(f"Alpaca returned no trade price for {symbol}")
        return price

    def is_market_open(self, symbol: str) -> bool:
        try:
            clock = self._client.get_clock()
        except APIError as e:
            raise DataUnavailable(f"Alpaca clock fetch failed: {e}") from e
        return bool(_field(clock, "is_open"))
