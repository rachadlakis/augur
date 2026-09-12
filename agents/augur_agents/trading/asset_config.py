"""Asset-class-aware configuration and utilities."""

from __future__ import annotations

from enum import Enum
from typing import Literal


class AssetClass(str, Enum):
    """Supported asset classes."""

    CRYPTO = "crypto"
    EQUITY = "equity"


AssetClassType = Literal["crypto", "equity"]


class AssetConfig:
    """Asset-class-specific settings and feature availability."""

    def __init__(self, asset_class: AssetClassType) -> None:
        self.asset_class = asset_class
        self.has_onchain = asset_class == "crypto"
        self.has_fundamentals = asset_class == "equity"
        self.has_derivatives = True  # both
        self.has_news = True  # both
        self.trading_hours = "24/7" if asset_class == "crypto" else "9:30-16:00 ET"
        self.settlement_time = "instant" if asset_class == "crypto" else "T+1"

    def get_applicable_agents(self) -> list[str]:
        agents = ["technical", "news", "derivatives", "macro"]
        if self.has_onchain:
            agents.append("onchain")
        if self.has_fundamentals:
            agents.append("fundamentals")
        return sorted(agents)
