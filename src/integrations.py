"""
Registry of every outside service Augur can connect to, in plain words.

One list feeds the dashboard's Integrations screen, the `/api/integrations`
endpoint, and `scripts/setup_integrations.py`, so they can never disagree.
Status reports only whether a key is present; key values never leave here.
"""

from dataclasses import dataclass, field
from pathlib import Path

from config import ENV_FILE, Settings


@dataclass(frozen=True)
class Integration:
    id: str
    name: str
    emoji: str
    what_it_does: str          # one sentence a beginner understands
    category: str              # "broker" | "data"
    signup_url: str
    key_url: str               # where the keys are created after signing up
    env_vars: tuple[str, ...]  # .env names, in the order the wizard asks for them
    required: bool = False
    safe_mode_var: str | None = None     # flag that keeps it on fake money
    steps: tuple[str, ...] = field(default=())


INTEGRATIONS: tuple[Integration, ...] = (
    Integration(
        id="alpaca",
        name="Alpaca",
        emoji="📈",
        what_it_does="Lets Augur buy and sell stocks, using practice money until you switch it off.",
        category="broker",
        signup_url="https://app.alpaca.markets/signup",
        key_url="https://app.alpaca.markets/paper/dashboard/overview",
        env_vars=("ALPACA_API_KEY", "ALPACA_SECRET_KEY"),
        required=True,
        safe_mode_var="ALPACA_PAPER",
        steps=(
            "Make a free account at alpaca.markets.",
            "Switch the top-left menu to 'Paper Trading' (practice money).",
            "Click 'Generate New Keys' on the right side of the page.",
            "Copy the Key ID and the Secret Key; the secret is shown only once.",
        ),
    ),
    Integration(
        id="binance",
        name="Binance Testnet",
        emoji="🪙",
        what_it_does="Lets Augur trade crypto like Bitcoin on Binance's practice exchange.",
        category="broker",
        signup_url="https://testnet.binance.vision/",
        key_url="https://testnet.binance.vision/",
        env_vars=("BINANCE_API_KEY", "BINANCE_API_SECRET"),
        safe_mode_var="BINANCE_TESTNET",
        steps=(
            "Open testnet.binance.vision and log in with GitHub.",
            "Click 'Generate HMAC_SHA256 Key' and give it any name.",
            "Copy the API Key and the Secret Key.",
        ),
    ),
    Integration(
        id="newsapi",
        name="NewsAPI",
        emoji="📰",
        what_it_does="Brings in news headlines so Augur knows what is happening.",
        category="data",
        signup_url="https://newsapi.org/register",
        key_url="https://newsapi.org/account",
        env_vars=("NEWSAPI_KEY",),
        steps=("Register at newsapi.org.", "Copy the API key shown on your account page."),
    ),
    Integration(
        id="cryptopanic",
        name="CryptoPanic",
        emoji="🚨",
        what_it_does="Crypto news and alerts.",
        category="data",
        signup_url="https://cryptopanic.com/developers/api/",
        key_url="https://cryptopanic.com/developers/api/keys",
        env_vars=("CRYPTOPANIC_API_KEY",),
        steps=("Sign up at cryptopanic.com.", "Open Developers → API keys and copy your key."),
    ),
    Integration(
        id="polygon",
        name="Polygon",
        emoji="📊",
        what_it_does="Price history for stocks, so charts and signals have data.",
        category="data",
        signup_url="https://polygon.io/dashboard/signup",
        key_url="https://polygon.io/dashboard/api-keys",
        env_vars=("POLYGON_API_KEY",),
        steps=("Sign up at polygon.io (free plan is fine).", "Copy the key from the API Keys page."),
    ),
    Integration(
        id="coingecko",
        name="CoinGecko",
        emoji="🦎",
        what_it_does="Crypto prices and market sizes.",
        category="data",
        signup_url="https://www.coingecko.com/en/developers/dashboard",
        key_url="https://www.coingecko.com/en/developers/dashboard",
        env_vars=("COINGECKO_API_KEY",),
        steps=("Create a free Demo account on CoinGecko.", "Copy the key from the developer dashboard."),
    ),
    Integration(
        id="glassnode",
        name="Glassnode",
        emoji="🔗",
        what_it_does="On-chain data: how coins move between wallets and exchanges.",
        category="data",
        signup_url="https://studio.glassnode.com/",
        key_url="https://studio.glassnode.com/settings/api",
        env_vars=("GLASSNODE_API_KEY",),
        steps=("Sign up at glassnode.com.", "Open Settings → API and copy your key."),
    ),
    Integration(
        id="fred",
        name="FRED",
        emoji="🏦",
        what_it_does="Economy numbers like interest rates from the US central bank's data site.",
        category="data",
        signup_url="https://fredaccount.stlouisfed.org/login/secure/",
        key_url="https://fredaccount.stlouisfed.org/apikeys",
        env_vars=("FRED_API_KEY",),
        steps=("Make a free account at fred.stlouisfed.org.", "Request an API key on the API Keys page."),
    ),
)

BY_ID = {integration.id: integration for integration in INTEGRATIONS}


def _is_set(settings: Settings, env_var: str) -> bool:
    value = getattr(settings, env_var.lower(), "")
    value = value.get_secret_value() if hasattr(value, "get_secret_value") else value
    return bool(str(value).strip())


def status(settings: Settings) -> list[dict]:
    """What is connected, without ever including a key value."""
    rows = []
    for integration in INTEGRATIONS:
        present = [_is_set(settings, var) for var in integration.env_vars]
        safe_mode = None
        if integration.safe_mode_var:
            safe_mode = bool(getattr(settings, integration.safe_mode_var.lower()))
        rows.append({
            "id": integration.id,
            "name": integration.name,
            "emoji": integration.emoji,
            "what_it_does": integration.what_it_does,
            "category": integration.category,
            "required": integration.required,
            "configured": all(present),
            "keys_present": sum(present),
            "keys_needed": len(present),
            "env_vars": list(integration.env_vars),
            "safe_mode": safe_mode,
            "signup_url": integration.signup_url,
            "key_url": integration.key_url,
            "steps": list(integration.steps),
        })
    return rows


def write_env(values: dict[str, str], env_file: Path = ENV_FILE) -> None:
    """Merge values into .env, keeping every other line (and comment) as it was."""
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    remaining = dict(values)
    out = []
    for line in lines:
        name = line.split("=", 1)[0].strip() if "=" in line and not line.lstrip().startswith("#") else None
        if name in remaining:
            out.append(f"{name}={remaining.pop(name)}")
        else:
            out.append(line)
    out.extend(f"{name}={value}" for name, value in remaining.items())
    env_file.write_text("\n".join(out) + "\n", encoding="utf-8")
