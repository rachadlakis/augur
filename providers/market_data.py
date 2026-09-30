"""
Historical bars from Alpaca for stocks/ETFs (gold, silver, oil funds) and crypto.
Read-only: nothing here can place an order.
"""

from datetime import datetime, timedelta, timezone

from alpaca.data.enums import DataFeed
from alpaca.data.historical import CryptoHistoricalDataClient, StockHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest, StockBarsRequest
from alpaca.data.timeframe import TimeFrame

from config import Settings
from providers.base import DataUnavailable


def _bars_to_dicts(barset, symbol: str) -> list[dict]:
    data = getattr(barset, "data", barset) or {}
    return [
        {
            "timestamp": bar.timestamp,
            "open": float(bar.open),
            "high": float(bar.high),
            "low": float(bar.low),
            "close": float(bar.close),
            "volume": float(bar.volume or 0.0),
        }
        for bar in data.get(symbol, [])
    ]


class AlpacaMarketData:
    """Hourly and daily bars, oldest first. Crypto symbols contain a slash (BTC/USD)."""

    def __init__(self, settings: Settings):
        api_key = settings.alpaca_api_key.get_secret_value() or None
        secret_key = settings.alpaca_secret_key.get_secret_value() or None
        self._stocks = StockHistoricalDataClient(api_key=api_key, secret_key=secret_key)
        self._crypto = CryptoHistoricalDataClient(api_key=api_key, secret_key=secret_key)

    def bars(self, symbol: str, timeframe: TimeFrame, lookback: timedelta) -> list[dict]:
        start = datetime.now(timezone.utc) - lookback
        try:
            if "/" in symbol:
                barset = self._crypto.get_crypto_bars(
                    CryptoBarsRequest(symbol_or_symbols=symbol, timeframe=timeframe, start=start)
                )
            else:
                # IEX is the feed free accounts may query for recent data.
                barset = self._stocks.get_stock_bars(
                    StockBarsRequest(symbol_or_symbols=symbol, timeframe=timeframe, start=start, feed=DataFeed.IEX)
                )
        except Exception as e:  # SDK raises several types; callers only need "no data"
            raise DataUnavailable(f"bars for {symbol} unavailable: {e}") from e
        bars = _bars_to_dicts(barset, symbol)
        if not bars:
            raise DataUnavailable(f"no {timeframe} bars returned for {symbol}")
        return bars

    def hourly_and_daily(self, symbol: str) -> tuple[list[dict], list[dict]]:
        return (
            self.bars(symbol, TimeFrame.Hour, timedelta(days=7)),
            self.bars(symbol, TimeFrame.Day, timedelta(days=45)),
        )
