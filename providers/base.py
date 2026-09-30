"""
Provider interfaces. Agent logic depends only on these — never on a
specific exchange/broker SDK directly. This is what lets Binance be
swapped for Coinbase, or Alpaca for Interactive Brokers, without
touching any agent code.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    STOP_LIMIT = "STOP_LIMIT"


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    limit_price: float | None = None
    stop_price: float | None = None
    # Exit protection submitted with the entry. A position must never be open
    # without its stop: set both to request a bracket.
    stop_loss: float | None = None
    take_profit: float | None = None

    @property
    def has_protection(self) -> bool:
        return self.stop_loss is not None or self.take_profit is not None


@dataclass(frozen=True)
class OrderResult:
    order_id: str
    status: str          # e.g. "FILLED", "REJECTED", "PENDING"
    filled_qty: float
    avg_fill_price: float | None
    raw_error: str | None = None
    # None: no protection requested. "ATTACHED": exits are live at the venue.
    # "FLATTENED": attaching failed, so the fill was closed. "UNPROTECTED": both
    # failed and the position is open without exits; treat as an incident.
    protection_status: str | None = None


@dataclass(frozen=True)
class AccountSnapshot:
    equity: float
    cash: float
    buying_power: float
    positions: dict[str, float]  # symbol -> quantity held
    # Holdings that could not be priced and are therefore NOT in `equity`.
    # Equity is a lower bound whenever this is non-empty.
    unpriced_assets: tuple[str, ...] = ()


@dataclass(frozen=True)
class PositionSnapshot:
    symbol: str
    quantity: float                 # always positive; direction is in `side`
    side: OrderSide                 # BUY = long, SELL = short
    avg_entry_price: float | None   # None when the venue does not report it
    current_price: float | None


class DataUnavailable(Exception):
    """Raised instead of ever fabricating a missing data point."""


class ExecutionProvider(ABC):
    """Shared contract for both crypto exchanges and stock brokers."""

    @abstractmethod
    def get_account(self) -> AccountSnapshot: ...

    @abstractmethod
    def place_order(self, order: OrderRequest) -> OrderResult: ...

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    def get_last_price(self, symbol: str) -> float: ...

    @abstractmethod
    def is_market_open(self, symbol: str) -> bool:
        """Crypto: effectively always True. Stocks: checks session hours."""
        ...

    def get_positions(self) -> list[PositionSnapshot]:
        """Open positions with real entry and mark prices, never placeholders."""
        raise NotImplementedError(f"{type(self).__name__} does not implement get_positions")

    def close_position(self, symbol: str) -> OrderResult:
        """Cancel the symbol's open orders (e.g. bracket legs), then flatten it."""
        raise NotImplementedError(f"{type(self).__name__} does not implement close_position")

    def close_all_positions(self) -> list[OrderResult]:
        """Kill switch: cancel open orders and flatten every position."""
        raise NotImplementedError(f"{type(self).__name__} does not implement close_all_positions")


class NewsProvider(ABC):
    @abstractmethod
    def get_recent_news(self, symbol: str, lookback_minutes: int) -> list[dict]: ...


class MacroProvider(ABC):
    @abstractmethod
    def get_series(self, series_id: str) -> list[dict]: ...


class OnChainProvider(ABC):
    """Crypto only. Stock pipelines simply don't wire this in."""

    @abstractmethod
    def get_exchange_flows(self, asset: str, lookback_minutes: int) -> dict: ...
