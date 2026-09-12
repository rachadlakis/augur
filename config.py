"""
Central, typed configuration for the trading system.

All secrets come from environment variables (loaded from .env in dev).
Nothing here should ever be hard-coded or logged.
"""

from enum import Enum
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


class TradingMode(str, Enum):
    PAPER = "paper"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"  # Ignore extra environment variables not defined in this model
    )

    # Mode
    trading_mode: TradingMode = TradingMode.PAPER

    # Binance (crypto)
    binance_api_key: SecretStr = SecretStr("")
    binance_api_secret: SecretStr = SecretStr("")
    binance_testnet: bool = True

    # Alpaca (stocks)
    alpaca_api_key: SecretStr = SecretStr("")
    alpaca_secret_key: SecretStr = SecretStr("")
    alpaca_paper: bool = True

    # Data providers
    newsapi_key: SecretStr = SecretStr("")
    cryptopanic_api_key: SecretStr = SecretStr("")
    glassnode_api_key: SecretStr = SecretStr("")
    polygon_api_key: SecretStr = SecretStr("")
    coingecko_api_key: SecretStr = SecretStr("")
    fred_api_key: SecretStr = SecretStr("")

    # Optional on-chain wallet
    wallet_private_key: SecretStr = SecretStr("")
    wallet_rpc_url: str = ""

    # Trading dashboard
    initial_capital: float = 100000.0

    def require_live_safety_check(self) -> None:
        """
        Hard guard: refuse to run in LIVE mode unless the testnet/paper
        flags have been explicitly turned off. Prevents accidentally
        trading real money because a flag was left at its default.
        """
        if self.trading_mode is TradingMode.LIVE:
            if self.binance_testnet or self.alpaca_paper:
                raise RuntimeError(
                    "TRADING_MODE=live but BINANCE_TESTNET or ALPACA_PAPER "
                    "is still true. Refusing to start. Flip both flags "
                    "explicitly to go live."
                )


def load_settings() -> Settings:
    """Load settings once and validate them. Call this at startup only."""
    settings = Settings()
    settings.require_live_safety_check()
    return settings


if __name__ == "__main__":
    # Sanity check: confirms which keys are present WITHOUT printing values.
    s = load_settings()
    print(f"Trading mode: {s.trading_mode.value}")
    print(f"Binance key present: {bool(s.binance_api_key.get_secret_value())} "
          f"(testnet={s.binance_testnet})")
    print(f"Alpaca key present: {bool(s.alpaca_api_key.get_secret_value())} "
          f"(paper={s.alpaca_paper})")
    print(f"NewsAPI key present: {bool(s.newsapi_key.get_secret_value())}")
    print(f"Polygon key present: {bool(s.polygon_api_key.get_secret_value())}")
    print(f"FRED key present: {bool(s.fred_api_key.get_secret_value())}")
