"""
Binance implementation of ExecutionProvider.
Requires: pip install python-binance
"""

import math

from binance.client import Client as BinanceSDK
from binance.exceptions import BinanceAPIException

from config import Settings
from providers.base import (
    ExecutionProvider, OrderRequest, OrderResult, OrderSide, OrderType,
    AccountSnapshot, DataUnavailable, PositionSnapshot,
)

# How far past the stop trigger the OCO's stop-limit leg may fill. A gap
# beyond this leaves the leg resting; the monitor must still watch the stop.
STOP_LIMIT_BUFFER = 0.005


class BinanceProvider(ExecutionProvider):
    def __init__(self, settings: Settings):
        self._client = BinanceSDK(
            api_key=settings.binance_api_key.get_secret_value(),
            api_secret=settings.binance_api_secret.get_secret_value(),
            testnet=settings.binance_testnet,
        )
        self._symbol_info: dict[str, dict] = {}
        # Binance cancels need the symbol; remember it for every order we place.
        self._order_symbols: dict[str, str] = {}
        self.quote_asset = "USDT"

    def _balances(self) -> dict[str, tuple[float, float]]:
        """asset -> (free, locked) for every non-zero balance."""
        try:
            info = self._client.get_account()
        except BinanceAPIException as e:
            raise DataUnavailable(f"Binance account fetch failed: {e}") from e
        return {
            b["asset"]: (float(b["free"]), float(b["locked"]))
            for b in info["balances"]
            if float(b["free"]) + float(b["locked"]) > 0
        }

    def _prices(self) -> dict[str, float]:
        try:
            return {t["symbol"]: float(t["price"]) for t in self._client.get_all_tickers()}
        except BinanceAPIException as e:
            raise DataUnavailable(f"Binance price fetch failed: {e}") from e

    def get_account(self) -> AccountSnapshot:
        balances = self._balances()
        prices = self._prices()

        free_quote, locked_quote = balances.get(self.quote_asset, (0.0, 0.0))
        equity = free_quote + locked_quote
        unpriced = []
        for asset, (free, locked) in balances.items():
            if asset == self.quote_asset:
                continue
            price = prices.get(f"{asset}{self.quote_asset}")
            if price is None:
                unpriced.append(asset)  # reported, never guessed
            else:
                equity += (free + locked) * price

        return AccountSnapshot(
            equity=equity,
            cash=free_quote,
            buying_power=free_quote,  # spot: no margin
            positions={asset: free + locked for asset, (free, locked) in balances.items()},
            unpriced_assets=tuple(sorted(unpriced)),
        )

    def get_positions(self) -> list[PositionSnapshot]:
        balances = self._balances()
        prices = self._prices()
        return [
            PositionSnapshot(
                symbol=f"{asset}{self.quote_asset}",
                quantity=free + locked,
                side=OrderSide.BUY,
                avg_entry_price=None,  # spot balances carry no cost basis
                current_price=prices.get(f"{asset}{self.quote_asset}"),
            )
            for asset, (free, locked) in balances.items()
            if asset != self.quote_asset
        ]

    def _info(self, symbol: str) -> dict:
        if symbol not in self._symbol_info:
            info = self._client.get_symbol_info(symbol)
            if not info:
                raise DataUnavailable(f"Binance has no symbol info for {symbol}")
            self._symbol_info[symbol] = info
        return self._symbol_info[symbol]

    def _filter(self, symbol: str, filter_type: str, key: str) -> float:
        for f in self._info(symbol).get("filters", []):
            if f.get("filterType") == filter_type:
                return float(f[key])
        return 0.0

    def _round_qty(self, symbol: str, qty: float) -> float:
        step = self._filter(symbol, "LOT_SIZE", "stepSize")
        return round(math.floor(qty / step + 1e-9) * step, 12) if step > 0 else qty

    def _round_price(self, symbol: str, price: float) -> float:
        tick = self._filter(symbol, "PRICE_FILTER", "tickSize")
        return round(round(price / tick) * tick, 12) if tick > 0 else price

    def _submit(self, order: OrderRequest) -> dict:
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
        return self._client.create_order(**kwargs)

    def _held_qty(self, symbol: str, resp: dict) -> float:
        """Filled quantity net of any commission charged in the base asset."""
        qty = float(resp.get("executedQty", 0.0))
        if resp.get("side") == "BUY":
            base = self._info(symbol).get("baseAsset")
            qty -= sum(
                float(f.get("commission", 0.0))
                for f in resp.get("fills", [])
                if f.get("commissionAsset") == base
            )
        return qty

    def _attach_oco(self, order: OrderRequest, qty: float) -> None:
        """One-cancels-other exit: take-profit limit plus stop-limit, opposite side."""
        exit_side = "SELL" if order.side == OrderSide.BUY else "BUY"
        stop = float(order.stop_loss or 0.0)
        take_profit = float(order.take_profit or 0.0)
        stop_limit = stop * (1 - STOP_LIMIT_BUFFER) if exit_side == "SELL" else stop * (1 + STOP_LIMIT_BUFFER)
        self._client.create_oco_order(
            symbol=order.symbol,
            side=exit_side,
            quantity=self._round_qty(order.symbol, qty),
            price=self._round_price(order.symbol, take_profit),
            stopPrice=self._round_price(order.symbol, stop),
            stopLimitPrice=self._round_price(order.symbol, stop_limit),
            stopLimitTimeInForce="GTC",
        )

    def place_order(self, order: OrderRequest) -> OrderResult:
        if order.has_protection and (
            order.order_type != OrderType.MARKET or order.stop_loss is None or order.take_profit is None
        ):
            # Spot has no native bracket: the exit is attached right after a
            # market fill, which needs both legs and an immediate fill.
            return OrderResult(
                order_id="", status="REJECTED", filled_qty=0.0, avg_fill_price=None,
                raw_error="protected Binance entries must be MARKET with both stop_loss and take_profit",
            )

        try:
            resp = self._submit(order)
        except BinanceAPIException as e:
            return OrderResult(
                order_id="", status="REJECTED",
                filled_qty=0.0, avg_fill_price=None, raw_error=str(e),
            )

        order_id = str(resp["orderId"])
        self._order_symbols[order_id] = order.symbol
        filled_qty = float(resp.get("executedQty", 0.0))
        avg_fill_price = float(resp["fills"][0]["price"]) if resp.get("fills") else None
        if not order.has_protection or filled_qty <= 0:
            return OrderResult(
                order_id=order_id, status=resp["status"],
                filled_qty=filled_qty, avg_fill_price=avg_fill_price,
            )

        held = self._held_qty(order.symbol, resp)
        error: str | None = None
        try:
            self._attach_oco(order, held)
            protection_status = "ATTACHED"
        except (BinanceAPIException, DataUnavailable) as e:
            # Never leave the fill naked: close it and report why.
            error = f"protection failed, position flattened: {e}"
            protection_status = "FLATTENED"
            try:
                self._submit(OrderRequest(
                    symbol=order.symbol,
                    side=OrderSide.SELL if order.side == OrderSide.BUY else OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    quantity=self._round_qty(order.symbol, held),
                ))
            except (BinanceAPIException, DataUnavailable) as flatten_error:
                error = f"protection failed AND flatten failed, position is UNPROTECTED: {e}; {flatten_error}"
                protection_status = "UNPROTECTED"

        return OrderResult(
            order_id=order_id, status=resp["status"],
            filled_qty=filled_qty, avg_fill_price=avg_fill_price,
            raw_error=error, protection_status=protection_status,
        )

    def close_position(self, symbol: str) -> OrderResult:
        try:
            for open_order in self._client.get_open_orders(symbol=symbol):
                self._client.cancel_order(symbol=symbol, orderId=open_order["orderId"])
            base = self._info(symbol).get("baseAsset")
            free = float(self._client.get_asset_balance(asset=base)["free"])
            qty = self._round_qty(symbol, free)
        except (BinanceAPIException, DataUnavailable) as e:
            return OrderResult(order_id="", status="REJECTED", filled_qty=0.0, avg_fill_price=None, raw_error=str(e))
        if qty <= 0:
            return OrderResult(
                order_id="", status="REJECTED", filled_qty=0.0, avg_fill_price=None,
                raw_error=f"no sellable {base} balance above the lot size",
            )
        return self.place_order(OrderRequest(symbol=symbol, side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=qty))

    def close_all_positions(self, quote_asset: str | None = None) -> list[OrderResult]:
        quote_asset = quote_asset or self.quote_asset
        try:
            for open_order in self._client.get_open_orders():
                self._client.cancel_order(symbol=open_order["symbol"], orderId=open_order["orderId"])
            balances = self._client.get_account()["balances"]
        except BinanceAPIException as e:
            return [OrderResult(order_id="", status="REJECTED", filled_qty=0.0, avg_fill_price=None, raw_error=str(e))]

        results: list[OrderResult] = []
        for balance in balances:
            asset, free = balance["asset"], float(balance["free"])
            if asset == quote_asset or free <= 0:
                continue
            symbol = f"{asset}{quote_asset}"
            try:
                qty = self._round_qty(symbol, free)
            except (BinanceAPIException, DataUnavailable) as e:
                results.append(OrderResult(order_id="", status="REJECTED", filled_qty=0.0, avg_fill_price=None, raw_error=str(e)))
                continue
            if qty <= 0:
                continue  # dust below the lot size cannot be sold
            results.append(self.place_order(OrderRequest(
                symbol=symbol, side=OrderSide.SELL, order_type=OrderType.MARKET, quantity=qty,
            )))
        return results

    def cancel_order(self, order_id: str) -> bool:
        symbol = self._order_symbols.get(order_id)
        if symbol is None:
            return False  # not placed by this provider instance; symbol unknown
        try:
            self._client.cancel_order(symbol=symbol, orderId=int(order_id))
        except BinanceAPIException:
            return False
        return True

    def get_last_price(self, symbol: str) -> float:
        try:
            ticker = self._client.get_symbol_ticker(symbol=symbol)
            return float(ticker["price"])
        except BinanceAPIException as e:
            raise DataUnavailable(f"Binance price fetch failed for {symbol}: {e}") from e

    def is_market_open(self, symbol: str) -> bool:
        return True  # crypto markets don't close
