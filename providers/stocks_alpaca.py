"""
Alpaca implementation of ExecutionProvider.
Requires: pip install alpaca-py
"""

from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest, StopOrderRequest
from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce
from alpaca.common.exceptions import APIError

from config import Settings
from providers.base import (
    ExecutionProvider, OrderRequest, OrderResult, OrderType,
    AccountSnapshot, DataUnavailable,
)


class AlpacaProvider(ExecutionProvider):
    def __init__(self, settings: Settings):
        self._client = TradingClient(
            api_key=settings.alpaca_api_key.get_secret_value(),
            secret_key=settings.alpaca_secret_key.get_secret_value(),
            paper=settings.alpaca_paper,
        )

    def get_account(self) -> AccountSnapshot:
        try:
            acct = self._client.get_account()
            positions = self._client.get_all_positions()
        except APIError as e:
            raise DataUnavailable(f"Alpaca account fetch failed: {e}") from e

        # Handle both TradeAccount object and dict responses
        if isinstance(acct, dict):
            equity = float(acct.get("equity", 0)) if acct.get("equity") is not None else 0.0
            cash = float(acct.get("cash", 0)) if acct.get("cash") is not None else 0.0
            buying_power = float(acct.get("buying_power", 0)) if acct.get("buying_power") is not None else 0.0
        else:
            equity = float(acct.equity) if acct.equity is not None else 0.0
            cash = float(acct.cash) if acct.cash is not None else 0.0
            buying_power = float(acct.buying_power) if acct.buying_power is not None else 0.0

        positions = self._client.get_all_positions()
        position_dict = {}
        for p in positions:
            if isinstance(p, dict):
                symbol = p.get("symbol")
                qty = p.get("qty")
            else:
                # Handle Position object
                symbol = getattr(p, "symbol", None)
                qty = getattr(p, "qty", None)
            if symbol and qty is not None:
                position_dict[symbol] = float(qty)

        return AccountSnapshot(
            equity=equity,
            cash=cash,
            buying_power=buying_power,
            positions=position_dict,
        )

    def place_order(self, order: OrderRequest) -> OrderResult:
        side = AlpacaSide.BUY if order.side.value == "BUY" else AlpacaSide.SELL

        try:
            req: MarketOrderRequest | LimitOrderRequest | StopOrderRequest
            if order.order_type == OrderType.MARKET:
                req = MarketOrderRequest(
                    symbol=order.symbol, qty=order.quantity,
                    side=side, time_in_force=TimeInForce.DAY,
                )
            elif order.order_type == OrderType.LIMIT:
                limit_price = float(order.limit_price) if order.limit_price is not None else 0.0
                req = LimitOrderRequest(
                    symbol=order.symbol, qty=order.quantity, side=side,
                    time_in_force=TimeInForce.DAY, limit_price=limit_price,
                )
            else:  # STOP_MARKET / STOP_LIMIT
                stop_price = float(order.stop_price) if order.stop_price is not None else 0.0
                req = StopOrderRequest(
                    symbol=order.symbol, qty=order.quantity, side=side,
                    time_in_force=TimeInForce.DAY, stop_price=stop_price,
                )
            resp = self._client.submit_order(req)
        except APIError as e:
            return OrderResult(
                order_id="", status="REJECTED",
                filled_qty=0.0, avg_fill_price=None, raw_error=str(e),
            )

        # Handle both Order object and dict responses
        if isinstance(resp, dict):
            order_id = str(resp.get("id", ""))
            status = str(resp.get("status", ""))
            filled_qty = float(resp.get("filled_qty") or 0.0)
            filled_avg = resp.get("filled_avg_price")
            avg_fill_price = float(filled_avg) if filled_avg is not None else None
        else:
            order_id = str(resp.id)
            status = str(resp.status)
            filled_qty = float(resp.filled_qty or 0.0)
            avg_fill_price = float(resp.filled_avg_price) if resp.filled_avg_price else None

        return OrderResult(
            order_id=order_id,
            status=status,
            filled_qty=filled_qty,
            avg_fill_price=avg_fill_price,
        )

    def cancel_order(self, order_id: str) -> bool:
        try:
            self._client.cancel_order_by_id(order_id)
            return True
        except APIError:
            return False

    def get_last_price(self, symbol: str) -> float:
        # Note: TradingClient doesn't serve quotes — use alpaca.data.StockHistoricalDataClient
        # for real price feeds. Left as a clear extension point rather than faked.
        raise NotImplementedError("Wire up alpaca.data.StockHistoricalDataClient for quotes")

    def is_market_open(self, symbol: str) -> bool:
        try:
            clock = self._client.get_clock()
            if isinstance(clock, dict):
                return bool(clock.get("is_open", False))
            else:
                return bool(clock.is_open)
        except APIError as e:
            raise DataUnavailable(f"Alpaca clock fetch failed: {e}") from e
