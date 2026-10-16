"""Politics/economics news and whale flows: parsing, failure modes, and how much they may move a trade.

No network: every HTTP call goes through a fake opener.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from augur_agents.contracts import MarketSnapshot
from augur_agents.trading.pipeline import TradingPipeline
from augur_agents.trading.specialists import PolicyRiskAnalyst, WhaleFlowAnalyst

from providers import news, whales
from providers.base import DataUnavailable

NOW = datetime(2026, 10, 16, 12, tzinfo=timezone.utc)


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def opener_returning(body: bytes | str):
    data = body.encode() if isinstance(body, str) else body
    return lambda request, timeout=None: Response(data)


# --- GDELT ----------------------------------------------------------------------------


def tone_payload(recent: float, baseline: float) -> str:
    points = []
    for hours_back in range(7 * 24, -1, -1):
        when = NOW - timedelta(hours=hours_back)
        points.append({"date": when.strftime("%Y%m%dT%H%M%SZ"), "value": recent if hours_back < 24 else baseline})
    return json.dumps({"timeline": [{"series": "Average Tone", "data": points}]})


def test_gdelt_tone_shift_is_recent_day_against_the_week_before():
    result = news.theme_tone("x", opener=opener_returning(tone_payload(-3.0, -1.0)), sleep=lambda s: None)
    assert result["tone"] == pytest.approx(-3.0, abs=0.1)
    assert result["baseline"] == pytest.approx(-1.0)
    assert result["shift"] == pytest.approx(-2.0, abs=0.1)


def test_gdelt_rate_limit_notice_is_unavailable_not_parsed():
    notice = opener_returning("Please limit requests to one every 5 seconds")
    with pytest.raises(DataUnavailable, match="rate-limited"):
        news.theme_tone("x", opener=notice, sleep=lambda s: None)


def test_gdelt_requests_are_spaced(monkeypatch):
    waits: list[float] = []
    monkeypatch.setattr(news, "_last_gdelt_call", 0.0)
    opener = opener_returning(tone_payload(-1.0, -1.0))
    news.theme_tone("a", opener=opener, sleep=waits.append)
    news.theme_tone("b", opener=opener, sleep=waits.append)
    assert waits and waits[-1] > 5.0


# --- Fed press releases --------------------------------------------------------------

FED_RSS = """<?xml version="1.0" encoding="utf-8" ?>
<rss version="2.0"><channel>
<item><title>Federal Reserve issues FOMC statement</title><pubDate>Fri, 16 Oct 2026 11:00:00 GMT</pubDate></item>
<item><title>Minutes of the Board's discount rate meetings</title><pubDate>Thu, 15 Oct 2026 18:00:00 GMT</pubDate></item>
<item><title>Minutes of the Federal Open Market Committee, September 15-16</title><pubDate>Wed, 07 Oct 2026 18:00:00 GMT</pubDate></item>
</channel></rss>"""


def test_fed_feed_finds_the_latest_fomc_release_only():
    events = news.fed_events(now=NOW, opener=opener_returning(FED_RSS))
    assert events["latest_fomc_hours_ago"] == pytest.approx(1.0)
    assert len(events["releases"]) == 2  # discount-rate minutes are not FOMC


def test_policy_uncertainty_percentile():
    values = [{"value": str(v)} for v in [300.0] * 7 + [100.0 + i * 0.1 for i in range(393)]]
    result = news.policy_uncertainty("key", opener=opener_returning(json.dumps({"observations": values})))
    assert result["percentile_1y"] == 1.0
    assert result["week_mean"] == 300.0


# --- Policy analyst ------------------------------------------------------------------


def test_dark_news_and_high_uncertainty_is_risk_off_and_gold_is_the_mirror():
    context = {"epu": {"percentile_1y": 0.97}, "themes": {"conflict": {"shift": -2.0}, "trade": {"shift": -1.0}}}
    stocks = PolicyRiskAnalyst().analyze(context)
    gold = PolicyRiskAnalyst().analyze(context, safe_haven=True)
    assert stocks["signal"] == "SELL" and gold["signal"] == "BUY"
    assert stocks["confidence"] <= 0.5
    assert "policy_uncertainty_high" in stocks["risk_flags"]


def test_calm_news_is_neutral_and_missing_news_abstains():
    assert PolicyRiskAnalyst().analyze({"epu": {"percentile_1y": 0.5}, "themes": {"rates": {"shift": 0.1}}})["signal"] == "NEUTRAL"
    assert PolicyRiskAnalyst().analyze({})["signal"] == "NO_TRADE"


def test_garbage_numbers_are_ignored():
    context = {"epu": {"percentile_1y": float("nan")}, "themes": {"x": {"shift": "lots"}, "y": {"shift": float("inf")}}}
    assert PolicyRiskAnalyst().analyze(context)["signal"] == "NO_TRADE"


# --- Whale analyst -------------------------------------------------------------------


def flows(stable_in=0.0, stable_out=0.0, eth_in=0.0, eth_out=0.0, biggest_usd=0.0):
    return {
        "stablecoins": {"inflow_usd": stable_in, "outflow_usd": stable_out, "netflow_usd": stable_in - stable_out,
                        "hours": 1, "largest": [{"usd": biggest_usd}]},
        "eth": {"inflow_eth": eth_in, "outflow_eth": eth_out, "netflow_eth": eth_in - eth_out, "largest": []},
    }


def test_stablecoins_arriving_lean_buy_and_eth_arriving_leans_sell():
    analyst = WhaleFlowAnalyst()
    assert analyst.analyze(flows(stable_in=80e6, stable_out=10e6, biggest_usd=10e6), asset="BTC/USD")["signal"] == "BUY"
    assert analyst.analyze(flows(eth_in=9000, eth_out=500), asset="ETH/USD")["signal"] == "SELL"
    # ETH flows say nothing about BTC.
    assert analyst.analyze(flows(eth_in=9000, eth_out=500), asset="BTC/USD")["signal"] == "NEUTRAL"


def test_small_balanced_or_single_wallet_flows_are_discounted():
    analyst = WhaleFlowAnalyst()
    assert analyst.analyze(flows(stable_in=5e6), asset="BTC/USD")["signal"] == "NEUTRAL"  # too small
    assert analyst.analyze(flows(stable_in=50e6, stable_out=45e6), asset="BTC/USD")["signal"] == "NEUTRAL"  # balanced
    one_whale = analyst.analyze(flows(stable_in=100e6, stable_out=20e6, biggest_usd=95e6), asset="BTC/USD")
    many = analyst.analyze(flows(stable_in=100e6, stable_out=20e6, biggest_usd=10e6), asset="BTC/USD")
    assert one_whale["flow_score"] < many["flow_score"]


def test_whales_never_vote_on_stocks():
    assert WhaleFlowAnalyst().analyze(flows(stable_in=80e6), asset="AAPL")["signal"] == "NO_TRADE"


# --- Whale provider ------------------------------------------------------------------


def test_stablecoin_flows_skip_exchange_internal_moves(monkeypatch):
    binance, coinbase = "0x28c6c06298d514db089934071355e5743bf21d60", "0x71660c4005ba85c37ccec55d0c4493e66fe775d3"
    outsider = "0x" + "ab" * 20

    def topic(addr):
        return "0x" + "0" * 24 + addr[2:]

    def rpc(method, params, rpc_url, opener):
        if method == "eth_blockNumber":
            return hex(1_000)
        topics = params[0]["topics"]
        if params[0]["fromBlock"] != hex(700):
            return []  # only answer the first chunk so each log is counted once
        if topics[1] is None:  # inflows query
            return [{"topics": [whales.TRANSFER_TOPIC, topic(outsider), topic(binance)], "data": hex(5_000_000 * 10**6)},
                    {"topics": [whales.TRANSFER_TOPIC, topic(coinbase), topic(binance)], "data": hex(99_000_000 * 10**6)}]
        return [{"topics": [whales.TRANSFER_TOPIC, topic(binance), topic(outsider)], "data": hex(1_000_000 * 10**6)}]

    monkeypatch.setattr(whales, "_rpc", rpc)
    result = whales.stablecoin_exchange_flows()
    assert result["inflow_usd"] == 5_000_000
    assert result["outflow_usd"] == 1_000_000
    assert result["largest"][0]["exchange"] == "Binance 14"


def test_exchange_wallets_can_be_extended_from_env():
    extra = whales.parse_exchange_wallets("0x" + "cd" * 20 + "=Bybit 1, not-an-address=Nope")
    assert extra["0x" + "cd" * 20] == "Bybit 1"
    assert "not-an-address" not in extra
    assert len(extra) == len(whales.EXCHANGE_WALLETS) + 1


def test_rpc_requests_name_a_user_agent():
    """Public gateways answer urllib's default User-Agent with 403."""
    seen = {}

    def opener(request, timeout=None):
        seen.update(request.headers)
        return Response(b'{"result": "0x1"}')

    whales._rpc("eth_blockNumber", [], "https://rpc.example", opener)
    assert seen.get("User-agent", "").startswith("augur")


# --- How much they may move a trade --------------------------------------------------


def snapshot(asset: str = "ETH/USD", move: float = 0.0) -> MarketSnapshot:
    bar = {"open": 100.0 / (1 + move), "high": 101.0, "low": 99.0, "close": 100.0, "volume": 1.0}
    flat = {"open": 100.0, "high": 100.1, "low": 99.9, "close": 100.0, "volume": 1.0}
    return MarketSnapshot(asset=asset, timestamp=NOW, price=100.0, ohlcv={"1h": flat, "4h": bar, "1d": bar},
                          volume=1.0, spread=0.0005, liquidity=0.9, volatility={"atr": 1.0})


def evaluate(**kw):
    args = dict(market_snapshot=snapshot(), account_equity=100_000.0, exposure=0.0, daily_loss_used=0.0, spread=0.0005,
                expected_slippage=0.0005, liquidity=0.9, macro_metrics={"dxy": 100.0, "fed_message": "neutral"}, now=NOW)
    args.update(kw)
    return TradingPipeline().evaluate(**args)


def test_maximal_bullish_news_and_whales_cannot_trade_a_flat_market():
    bullish_policy = {"epu": {"percentile_1y": 0.0}, "themes": {t: {"shift": 5.0} for t in news.THEMES}}
    result = evaluate(policy_context=bullish_policy, whale_flows=flows(stable_in=500e6, stable_out=1e6, eth_out=50_000))
    assert result["order"] is None


def test_fomc_release_blocks_entries_and_uncertainty_halves_size():
    strong = dict(market_snapshot=snapshot(move=0.03),
                  macro_metrics={"dxy": 98.0, "fed_message": "dovish", "horizon_hours": 24})
    baseline = evaluate(**strong)
    assert baseline["order"] is not None

    blocked = evaluate(**strong, policy_context={"fomc_hours_ago": 0.5})
    assert blocked["order"] is None
    assert any("FOMC" in v for v in blocked["vetoes"])

    halved = evaluate(**strong, policy_context={"epu": {"percentile_1y": 0.95}})
    if halved["order"] is not None:  # the policy lean may also veto it outright, which is fine
        assert halved["order"]["notional"] <= baseline["order"]["notional"] * 0.5 + 1e-6


def test_intel_endpoint_serves_readings_without_network(monkeypatch):
    import importlib.util
    import sys
    from pathlib import Path

    from fastapi.testclient import TestClient

    path = Path(__file__).resolve().parents[1] / "src" / "dashboard_api.py"
    spec = importlib.util.spec_from_file_location("dashboard_api_intel", path)
    dash = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = dash
    spec.loader.exec_module(dash)
    monkeypatch.setattr(dash, "trading_state", dash.TradingState(dash.Settings(), connect_broker=False))
    monkeypatch.setattr(dash.news_feeds, "macro_news_context",
                        lambda key: {"epu": {"percentile_1y": 0.95}, "themes": {"conflict": {"shift": -2.0}}})
    monkeypatch.setattr(dash.whales, "whale_flow_snapshot", lambda **kw: flows(stable_in=80e6, stable_out=5e6))

    body = TestClient(dash.app).get("/api/intel").json()
    assert body["readings"]["policy_for_risk_assets"]["signal"] == "SELL"
    assert body["readings"]["policy_for_gold"]["signal"] == "BUY"
    assert body["readings"]["whales_for_btc"]["signal"] == "BUY"
    assert body["refreshed_at"]


def test_gdelt_rate_limit_stops_the_round_instead_of_hammering(monkeypatch):
    import urllib.error

    calls = []

    def throttled(request, timeout=None):
        calls.append(request.full_url)
        raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {}, None)

    result = news.all_theme_tones(opener=throttled, sleep=lambda s: None)
    assert len(calls) == 1
    assert set(result["errors"]) == set(news.THEMES)
    assert result["themes"] == {}
