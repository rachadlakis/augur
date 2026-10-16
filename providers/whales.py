"""
Whale flows on Ethereum: big money moving onto and off exchanges.

What the evidence supports, and what this module therefore measures:

* Stablecoin (USDT) net inflows to exchanges have positively predicted BTC and
  ETH returns at 1-6 hour horizons: dollars arriving to buy.
* ETH net inflows to exchanges have negatively predicted ETH returns over the
  same horizons: coins arriving to be sold. Outflows were not reliably
  predictive. (Both: "Return and Volatility Forecasting Using On-Chain Flows
  in Cryptocurrency Markets", arXiv:2411.06327, 2017-2023 data.)
* Blindly copying "whale wallets" is not supported: the biggest wallets are
  mostly exchanges, ETFs and custodians, and analysts who track them report
  no reliable edge. So Augur reads flows *into and out of exchanges*, and
  only as confirming evidence, never as a reason to trade on its own.

Reads go through any public Ethereum JSON-RPC endpoint; no key, no signing.
"""

from __future__ import annotations

import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from providers.base import DataUnavailable
from providers.wallets import DEFAULT_RPC_URL, RPC_HEADERS, WEI_PER_ETH

# Exchange hot wallets, labels checked against Etherscan's public name tags on
# 2026-10-16. Lower-case. Extend with EXCHANGE_WALLETS in .env (addr=label,...).
EXCHANGE_WALLETS: dict[str, str] = {
    "0x28c6c06298d514db089934071355e5743bf21d60": "Binance 14",
    "0x21a31ee1afc51d94c2efccaa2092ad1028285549": "Binance 15",
    "0xdfd5293d8e347dfe59e90efd55b2956a1343963d": "Binance 16",
    "0x71660c4005ba85c37ccec55d0c4493e66fe775d3": "Coinbase 1",
    "0x503828976d22510aad0201ac7ec88293211d23da": "Coinbase 12",
    "0x2910543af39aba0cd09dbb2d50200b3e800a63d2": "Kraken 1",
    "0x6cc5f688a315f3dc28a7781717a9a798a59fda7b": "OKX",
}

USDT_CONTRACT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
USDT_DECIMALS = 6
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
BLOCKS_PER_HOUR = 300  # ~12 s blocks
LOG_CHUNK_BLOCKS = 100  # public nodes cap eth_getLogs ranges

Opener = Callable[..., Any]


def parse_exchange_wallets(extra: str) -> dict[str, str]:
    """`0xabc...=Label,0xdef...=Other` from .env, merged over the built-in list."""
    wallets = dict(EXCHANGE_WALLETS)
    for entry in (extra or "").split(","):
        address, _, label = entry.strip().partition("=")
        address = address.strip().lower()
        if len(address) == 42 and address.startswith("0x"):
            wallets[address] = label.strip() or address[:10]
    return wallets


def _rpc(method: str, params: list, rpc_url: str, opener: Opener) -> Any:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    request = urllib.request.Request(rpc_url, data=body, headers=RPC_HEADERS)
    try:
        with opener(request, timeout=20) as response:
            payload = json.load(response)
    except Exception as e:
        raise DataUnavailable(f"RPC {method} failed: {e}") from e
    if "error" in payload or "result" not in payload:
        raise DataUnavailable(f"RPC {method} error: {payload.get('error')}")
    return payload["result"]


def _topic(address: str) -> str:
    return "0x" + "0" * 24 + address[2:].lower()


def _address(topic: str) -> str:
    return "0x" + topic[-40:].lower()


def stablecoin_exchange_flows(
    *, hours: float = 1.0, rpc_url: str = DEFAULT_RPC_URL, exchanges: dict[str, str] | None = None,
    opener: Opener = urllib.request.urlopen,
) -> dict[str, Any]:
    """USDT moved onto and off the known exchange wallets over the last `hours`.

    Exchange-to-exchange transfers are internal reshuffles, not demand, and
    are left out.
    """
    exchanges = exchanges or EXCHANGE_WALLETS
    latest = int(_rpc("eth_blockNumber", [], rpc_url, opener), 16)
    start = latest - int(hours * BLOCKS_PER_HOUR)
    topics = [_topic(a) for a in exchanges]

    def logs(direction_topics: list) -> list[dict]:
        out: list[dict] = []
        for chunk_start in range(start, latest + 1, LOG_CHUNK_BLOCKS):
            chunk_end = min(latest, chunk_start + LOG_CHUNK_BLOCKS - 1)
            out += _rpc("eth_getLogs", [{
                "fromBlock": hex(chunk_start), "toBlock": hex(chunk_end), "address": USDT_CONTRACT,
                "topics": direction_topics,
            }], rpc_url, opener)
        return out

    inflow = outflow = 0.0
    largest: list[dict[str, Any]] = []
    for direction, entries in (("to_exchange", logs([TRANSFER_TOPIC, None, topics])),
                               ("from_exchange", logs([TRANSFER_TOPIC, topics, None]))):
        for entry in entries:
            sender, receiver = _address(entry["topics"][1]), _address(entry["topics"][2])
            if sender in exchanges and receiver in exchanges:
                continue
            amount = int(entry.get("data") or "0x0", 16) / 10**USDT_DECIMALS
            if direction == "to_exchange":
                inflow += amount
            else:
                outflow += amount
            largest.append({"direction": direction, "usd": round(amount, 2), "tx": entry.get("transactionHash"),
                            "exchange": exchanges.get(receiver if direction == "to_exchange" else sender)})
    largest.sort(key=lambda t: t["usd"], reverse=True)
    return {"asset": "USDT", "hours": hours, "from_block": start, "to_block": latest,
            "inflow_usd": round(inflow, 2), "outflow_usd": round(outflow, 2),
            "netflow_usd": round(inflow - outflow, 2), "largest": largest[:10]}


def eth_whale_transfers(
    *, blocks: int = 50, min_eth: float = 100.0, rpc_url: str = DEFAULT_RPC_URL,
    exchanges: dict[str, str] | None = None, opener: Opener = urllib.request.urlopen,
) -> dict[str, Any]:
    """Native ETH transfers of at least `min_eth` in the last `blocks`, tagged by exchange involvement."""
    exchanges = exchanges or EXCHANGE_WALLETS
    latest = int(_rpc("eth_blockNumber", [], rpc_url, opener), 16)
    inflow = outflow = 0.0
    transfers: list[dict[str, Any]] = []
    # One block per request; a few in flight at once keeps a 50-block scan to seconds.
    with ThreadPoolExecutor(max_workers=6) as pool:
        fetched = list(pool.map(
            lambda n: _rpc("eth_getBlockByNumber", [hex(n), True], rpc_url, opener) or {},
            range(latest - blocks + 1, latest + 1),
        ))
    for block in fetched:
        for tx in block.get("transactions") or []:
            value = int(tx.get("value") or "0x0", 16) / WEI_PER_ETH
            if value < min_eth:
                continue
            sender, receiver = str(tx.get("from") or "").lower(), str(tx.get("to") or "").lower()
            to_ex, from_ex = receiver in exchanges, sender in exchanges
            if to_ex and from_ex:
                kind = "exchange_internal"
            elif to_ex:
                kind, inflow = "to_exchange", inflow + value
            elif from_ex:
                kind, outflow = "from_exchange", outflow + value
            else:
                kind = "wallet_to_wallet"
            transfers.append({"tx": tx.get("hash"), "eth": round(value, 4), "kind": kind, "from": sender, "to": receiver,
                              "exchange": exchanges.get(receiver) or exchanges.get(sender)})
    transfers.sort(key=lambda t: t["eth"], reverse=True)
    return {"asset": "ETH", "blocks": blocks, "to_block": latest, "min_eth": min_eth,
            "inflow_eth": round(inflow, 4), "outflow_eth": round(outflow, 4),
            "netflow_eth": round(inflow - outflow, 4), "largest": transfers[:15]}


def whale_flow_snapshot(
    *, rpc_url: str = DEFAULT_RPC_URL, extra_exchanges: str = "", opener: Opener = urllib.request.urlopen,
) -> dict[str, Any]:
    """Both flow readings; each source fails on its own and says why."""
    exchanges = parse_exchange_wallets(extra_exchanges)
    snapshot: dict[str, Any] = {"exchanges_tracked": len(exchanges), "errors": {}}
    try:
        snapshot["stablecoins"] = stablecoin_exchange_flows(rpc_url=rpc_url, exchanges=exchanges, opener=opener)
    except DataUnavailable as e:
        snapshot["errors"]["stablecoins"] = str(e)
    try:
        snapshot["eth"] = eth_whale_transfers(rpc_url=rpc_url, exchanges=exchanges, opener=opener)
    except DataUnavailable as e:
        snapshot["errors"]["eth"] = str(e)
    return snapshot
