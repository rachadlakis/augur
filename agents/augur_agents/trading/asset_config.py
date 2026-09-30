"""Asset-class-aware configuration and utilities."""

from __future__ import annotations

from enum import Enum
from typing import Literal


class AssetClass(str, Enum):
    """Supported asset classes."""

    CRYPTO = "crypto"
    EQUITY = "equity"
    COMMODITY = "commodity"


AssetClassType = Literal["crypto", "equity", "commodity"]


class AssetConfig:
    """Asset-class-specific settings and feature availability.

    Commodities (gold, silver, oil) are traded through exchange-traded funds,
    so they keep equity-style session hours but have no company fundamentals
    and no on-chain flows. Their extra input is the futures term structure,
    which drives the roll yield an ETF holder actually earns.
    """

    def __init__(self, asset_class: AssetClassType) -> None:
        if asset_class not in {"crypto", "equity", "commodity"}:
            raise ValueError(f"unknown asset class {asset_class!r}")
        self.asset_class = asset_class
        self.has_onchain = asset_class == "crypto"
        self.has_fundamentals = asset_class == "equity"
        self.has_term_structure = asset_class == "commodity"
        self.has_derivatives = True  # all
        self.has_news = True  # all
        self.trading_hours = "24/7" if asset_class == "crypto" else "9:30-16:00 ET"
        self.settlement_time = "instant" if asset_class == "crypto" else "T+1"

    def get_applicable_agents(self) -> list[str]:
        agents = ["technical", "news", "derivatives", "macro"]
        if self.has_onchain:
            agents.append("onchain")
        if self.has_fundamentals:
            agents.append("fundamentals")
        if self.has_term_structure:
            agents.append("term_structure")
        return sorted(agents)
