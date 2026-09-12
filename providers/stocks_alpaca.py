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

        return AccountSnapshot(
            equity=float(acct.equity),
            cash=float(acct.cash),
            buying_power=float(acct.buying_power),
            positions={p.symbol: float(p.qty) for p in positions},
        )

    def place_order(self, order: OrderRequest) -> OrderResult:
        side = AlpacaSide.BUY if order.side.value == "BUY" else AlpacaSide.SELL

        try:
            if order.order_type == OrderType.MARKET:
                req = MarketOrderRequest(
                    symbol=order.symbol, qty=order.quantity,
                    side=side, time_in_force=TimeInForce.DAY,
                )
            elif order.order_type == OrderType.LIMIT:
                req = LimitOrderRequest(
                    symbol=order.symbol, qty=order.quantity, side=side,
                    time_in_force=TimeInForce.DAY, limit_price=order.limit_price,
                )
            else:  # STOP_MARKET / STOP_LIMIT
                req = StopOrderRequest(
                    symbol=order.symbol, qty=order.quantity, side=side,
                    time_in_force=TimeInForce.DAY, stop_price=order.stop_price,
                )
            resp = self._client.submit_order(req)
        except APIError as e:
            return OrderResult(
                order_id="", status="REJECTED",
                filled_qty=0.0, avg_fill_price=None, raw_error=str(e),
            )

        return OrderResult(
            order_id=str(resp.id),
            status=str(resp.status),
            filled_qty=float(resp.filled_qty or 0.0),
            avg_fill_price=float(resp.filled_avg_price) if resp.filled_avg_price else None,
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
            return bool(clock.is_open)
        except APIError as e:
            raise DataUnavailable(f"Alpaca clock fetch failed: {e}") from e
