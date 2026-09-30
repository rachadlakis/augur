"""
Watch-only crypto wallets: read an Ethereum address's ETH balance over JSON-RPC.

Only public addresses are ever used. Augur has no code path that signs a
transaction, so a wallet here can be viewed but never spent from.
"""

import json
import re
import urllib.request

from providers.base import DataUnavailable

DEFAULT_RPC_URL = "https://ethereum-rpc.publicnode.com"
_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
_PRIVATE_KEY = re.compile(r"^(0x)?[0-9a-fA-F]{64}$")
WEI_PER_ETH = 10**18


def validate_address(address: str) -> str:
    """Return the address if it is a public Ethereum address; refuse anything else."""
    candidate = address.strip()
    if _PRIVATE_KEY.match(candidate):
        # 64 hex characters is a private key, not an address. Never accept or store it.
        raise ValueError("That looks like a PRIVATE KEY. Never paste it anywhere. Use the public address (0x + 40 characters).")
    if not _ADDRESS.match(candidate):
        raise ValueError("A public Ethereum address starts with 0x and has 40 more letters/numbers.")
    return candidate


def eth_balance(address: str, rpc_url: str = DEFAULT_RPC_URL, opener=urllib.request.urlopen) -> float:
    """ETH held by `address`, from the latest block."""
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "eth_getBalance", "params": [validate_address(address), "latest"]})
    request = urllib.request.Request(rpc_url, data=body.encode(), headers={"Content-Type": "application/json"})
    try:
        with opener(request, timeout=10) as response:
            payload = json.load(response)
    except Exception as e:
        raise DataUnavailable(f"wallet RPC request failed: {e}") from e
    if "error" in payload or "result" not in payload:
        raise DataUnavailable(f"wallet RPC error: {payload.get('error')}")
    return int(payload["result"], 16) / WEI_PER_ETH
