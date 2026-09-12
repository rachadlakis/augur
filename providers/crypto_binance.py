"""
Binance implementation of ExecutionProvider.
Requires: pip install python-binance
"""

from binance.client import Client as BinanceSDK
from binance.exceptions import BinanceAPIException

from config import Settings
from providers.base import (
    ExecutionProvider, OrderRequest, OrderResult,
    AccountSnapshot, DataUnavailable,
)


class BinanceProvider(ExecutionProvider):
    def __init__(self, settings: Settings):
        self._client = BinanceSDK(
            api_key=settings.binance_api_key.get_secret_value(),
            api_secret=settings.binance_api_secret.get_secret_value(),
            testnet=settings.binance_testnet,
        )

    def get_account(self) -> AccountSnapshot:
        try:
            info = self._client.get_account()
        except BinanceAPIException as e:
            raise DataUnavailable(f"Binance account fetch failed: {e}") from e

        positions = {
            b["asset"]: float(b["free"]) + float(b["locked"])
            for b in info["balances"]
            if float(b["free"]) + float(b["locked"]) > 0
        }
        usdt = positions.get("USDT", 0.0)
        return AccountSnapshot(
            equity=usdt,          # simplified: extend to mark-to-market all assets
            cash=usdt,
            buying_power=usdt,
            positions=positions,
        )

    def place_order(self, order: OrderRequest) -> OrderResult:
        try:
            kwargs = {
                "symbol": order.symbol,
                "side": order.side.value,
                "type": order.order_type.value,
                "quantity": order.quantity,
            }
            if order.limit_price is not None:
                kwargs["price"] = float(order.limit_price)
            if order.stop_price is not None:
                kwargs["stopPrice"] = float(order.stop_price)
            
            resp = self._client.create_order(**kwargs)
        except BinanceAPIException as e:
            return OrderResult(
                order_id="", status="REJECTED",
                filled_qty=0.0, avg_fill_price=None, raw_error=str(e),
            )

        return OrderResult(
            order_id=str(resp["orderId"]),
            status=resp["status"],
            filled_qty=float(resp.get("executedQty", 0.0)),
            avg_fill_price=float(resp["fills"][0]["price"]) if resp.get("fills") else None,
        )

    def cancel_order(self, order_id: str) -> bool:
        raise NotImplementedError("Wire up symbol + orderId per Binance's cancel_order API")

    def get_last_price(self, symbol: str) -> float:
        try:
            ticker = self._client.get_symbol_ticker(symbol=symbol)
            return float(ticker["price"])
        except BinanceAPIException as e:
            raise DataUnavailable(f"Binance price fetch failed for {symbol}: {e}") from e

    def is_market_open(self, symbol: str) -> bool:
        return True  # crypto markets don't close
