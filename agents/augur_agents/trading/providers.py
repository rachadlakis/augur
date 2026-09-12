"""Provider interfaces and adapters for market, news, and execution data."""

from __future__ import annotations

from typing import Any

DATA_UNAVAILABLE = {"status": "DATA_UNAVAILABLE", "error": "provider unavailable or no data"}


class ProviderBase:
    """Simple interface contract: no provider may invent a value when data fails."""

    def fetch(self, symbol: str, **kwargs: Any) -> Any:
        return DATA_UNAVAILABLE


class MarketDataProvider(ProviderBase):
    def fetch(self, symbol: str, **kwargs: Any) -> Any:
        return DATA_UNAVAILABLE


class NewsProvider(ProviderBase):
    def fetch(self, symbol: str, **kwargs: Any) -> Any:
        return DATA_UNAVAILABLE


class OnChainProvider(ProviderBase):
    def fetch(self, symbol: str, **kwargs: Any) -> Any:
        return DATA_UNAVAILABLE


class DerivativesProvider(ProviderBase):
    def fetch(self, symbol: str, **kwargs: Any) -> Any:
        return DATA_UNAVAILABLE


class MacroProvider(ProviderBase):
    def fetch(self, symbol: str, **kwargs: Any) -> Any:
        return DATA_UNAVAILABLE


class ExchangeProvider(ProviderBase):
    def fetch(self, symbol: str, **kwargs: Any) -> Any:
        return DATA_UNAVAILABLE
