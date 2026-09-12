"""
Run this after filling in .env to confirm both accounts are reachable
before wiring anything else up. Never prints key values.

Usage: python verify_connections.py
"""

from config import load_settings
from providers.crypto_binance import BinanceProvider
from providers.stocks_alpaca import AlpacaProvider
from providers.base import DataUnavailable


def check_binance(settings) -> None:
    if not settings.binance_api_key.get_secret_value():
        print("Binance: no key set, skipping.")
        return
    try:
        acct = BinanceProvider(settings).get_account()
        print(f"Binance OK — testnet={settings.binance_testnet}, "
              f"USDT balance={acct.equity}")
    except DataUnavailable as e:
        print(f"Binance FAILED: {e}")


def check_alpaca(settings) -> None:
    if not settings.alpaca_api_key.get_secret_value():
        print("Alpaca: no key set, skipping.")
        return
    try:
        provider = AlpacaProvider(settings)
        acct = provider.get_account()
        print(f"Alpaca OK — paper={settings.alpaca_paper}, "
              f"equity={acct.equity}, market_open={provider.is_market_open('AAPL')}")
    except DataUnavailable as e:
        print(f"Alpaca FAILED: {e}")


if __name__ == "__main__":
    settings = load_settings()
    print(f"Trading mode: {settings.trading_mode.value}\n")
    check_binance(settings)
    check_alpaca(settings)
