"""
Friendly setup wizard for Augur's connections.

    python scripts/setup_integrations.py            # guided setup
    python scripts/setup_integrations.py --status   # just show what's connected

Keys are typed hidden and saved only to the local .env file. The wizard keeps
practice mode on (paper trading / testnet) and can never switch it off; going
live is a deliberate manual edit.
"""

import argparse
import getpass
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for path in (ROOT, ROOT / "src"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import integrations  # noqa: E402
from config import ENV_FILE, Settings  # noqa: E402

SAFE_DEFAULTS = {"TRADING_MODE": "paper", "ALPACA_PAPER": "true", "BINANCE_TESTNET": "true"}


def show_status(settings: Settings) -> list[dict]:
    rows = integrations.status(settings)
    done = sum(r["configured"] for r in rows)
    print(f"\n  Connections: {done} of {len(rows)} ready\n")
    for i, row in enumerate(rows, 1):
        mark = "✅" if row["configured"] else ("⭐" if row["required"] else "  ")
        tag = "connected" if row["configured"] else ("START HERE" if row["required"] else "optional")
        print(f"  {i}. {mark} {row['emoji']} {row['name']:<16} {tag:<11} {row['what_it_does']}")
    print()
    return rows


def ensure_safe_defaults() -> None:
    """Write practice-mode flags only where the .env doesn't set them yet."""
    existing = ENV_FILE.read_text(encoding="utf-8") if ENV_FILE.exists() else ""
    names = {line.split("=", 1)[0].strip() for line in existing.splitlines() if "=" in line}
    missing = {k: v for k, v in SAFE_DEFAULTS.items() if k not in names}
    if missing:
        integrations.write_env(missing)


def test_connection(integration_id: str) -> None:
    settings = Settings()
    try:
        if integration_id == "alpaca":
            from providers.stocks_alpaca import AlpacaProvider
            account = AlpacaProvider(settings).get_account()
            money = "practice money" if settings.alpaca_paper else "REAL money"
            print(f"  🎉 Connected! Account has ${account.equity:,.2f} ({money}).")
        elif integration_id == "binance":
            from providers.crypto_binance import BinanceProvider
            account = BinanceProvider(settings).get_account()
            print(f"  🎉 Connected! Testnet wallet worth ${account.equity:,.2f}.")
        else:
            print("  👍 Saved. It will be used when that data feed is switched on.")
    except ImportError as e:
        print(f"  Saved, but a library is missing: {e}. Run: pip install -r requirements.txt")
    except Exception as e:
        print(f"  😕 That didn't work: {e}")
        print("     Check that you copied the whole key, with no spaces, and try again.")


def set_up(row: dict) -> None:
    integration = integrations.BY_ID[row["id"]]
    print(f"\n{integration.emoji}  {integration.name}: {integration.what_it_does}\n")
    for i, step in enumerate(integration.steps, 1):
        print(f"   Step {i}. {step}")
    if input("\n  Open the website now? [Y/n] ").strip().lower() in ("", "y", "yes"):
        webbrowser.open(integration.signup_url)

    values = {}
    for name in integration.env_vars:
        value = getpass.getpass(f"  Paste {name} (hidden, press Enter when done): ").strip()
        if not value:
            print("  Skipped.")
            return
        if any(c.isspace() for c in value):
            print("  That has spaces in it; keys never do. Skipped, try copying again.")
            return
        values[name] = value

    integrations.write_env(values)
    print(f"  Saved to {ENV_FILE.name}.")
    test_connection(integration.id)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--status", action="store_true", help="show connection status and exit")
    args = parser.parse_args()

    print("\n  ◆ Augur setup: let's plug in your accounts.\n  🛡️  Practice mode stays ON: no real money moves.")
    if args.status:
        show_status(Settings())
        return 0

    ensure_safe_defaults()
    while True:
        rows = show_status(Settings())
        choice = input("  Pick a number to set up (Enter to finish): ").strip()
        if not choice:
            print("\n  All set. Start Augur with:  python src/dashboard_api.py\n")
            return 0
        if not choice.isdigit() or not 1 <= int(choice) <= len(rows):
            print("  Type one of the numbers in the list.")
            continue
        set_up(rows[int(choice) - 1])


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyboardInterrupt, EOFError):
        print("\n  Bye! Run this again any time.")
        sys.exit(0)
