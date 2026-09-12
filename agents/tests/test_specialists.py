from __future__ import annotations

from datetime import datetime, timezone

import pytest

from augur_agents.contracts import MarketSnapshot
from augur_agents.trading.asset_config import AssetConfig
from augur_agents.trading.backtest import BaselineComparison, PaperTradingBacktester
from augur_agents.trading.pipeline import TradingPipeline
from augur_agents.trading.providers import (
    DATA_UNAVAILABLE,
    DerivativesProvider,
    ExchangeProvider,
    MacroProvider,
    MarketDataProvider,
    NewsProvider,
    OnChainProvider,
)
from augur_agents.trading.specialists import (
    DerivativesAnalyst,
    FundamentalsAnalyst,
    MacroAnalyst,
    NewsSentimentAnalyst,
    OnChainAnalyst,
    TechnicalAnalyst,
)


@pytest.fixture
def bullish_snapshot():
    return MarketSnapshot(
        asset="BTC/USD",
        timestamp=datetime.now(timezone.utc),
        price=50000.0,
        ohlcv={
            "15m": {"open": 49750.0, "high": 49950.0, "low": 49600.0, "close": 50000.0, "volume": 100.0},
            "1h": {"open": 49200.0, "high": 50200.0, "low": 49000.0, "close": 50000.0, "volume": 250.0},
            "4h": {"open": 48000.0, "high": 50500.0, "low": 47800.0, "close": 50000.0, "volume": 800.0},
            "1d": {"open": 46500.0, "high": 51000.0, "low": 46200.0, "close": 50000.0, "volume": 2400.0},
        },
        volume=5000.0,
        spread=0.0007,
        liquidity=0.82,
        volatility={"atr": 420.0, "realized_volatility": 0.05},
        derivatives={"funding_rate": 0.0001, "open_interest": 2.5, "basis": 0.002, "liquidation_data": {"shorts": 500, "longs": 450}},
    )


def test_technical_analyst_bullish_signal(bullish_snapshot):
    result = TechnicalAnalyst().analyze(bullish_snapshot)
    assert result["agent"] == "technical"
    assert result["signal"] in {"BUY", "HOLD"}
    assert 0.0 <= result["confidence"] <= 1.0
    assert result["evidence"]


def test_onchain_analyst_handles_transfer_uncertainty():
    result = OnChainAnalyst().analyze({
        "exchange_inflows": 3100,
        "exchange_outflows": 2800,
        "netflow": 300,
        "transfer_classification": "unknown",
        "whale_activity": "moderate",
    })
    assert result["agent"] == "onchain"
    assert result["signal"] in {"BUY", "SELL", "HOLD", "NEUTRAL"}
    assert "cannot distinguish" in result["interpretation"].lower()


def test_news_analyst_requires_evidence_not_just_counting():
    result = NewsSentimentAnalyst().analyze([
        {"headline": "ETF inflows accelerate amid strong institutional demand", "source": "official", "sentiment": 0.8, "impact": "HIGH_IMPACT", "published": datetime.now(timezone.utc)},
        {"headline": "anonymous social rumor about exchange outage", "source": "reddit", "sentiment": -0.7, "impact": "LOW_IMPACT", "published": datetime.now(timezone.utc)},
    ])
    assert result["signal"] in {"BUY", "HOLD", "NEUTRAL"}
    assert result["source_credibility"] >= 0.0
    assert result["impact_score"] >= 0.0


def test_derivatives_analyst_distinguishes_crowding_risk():
    result = DerivativesAnalyst().analyze({
        "funding_rate": 0.0008,
        "open_interest": 4.5,
        "basis": 0.01,
        "crowding_score": 0.9,
        "liquidation_risk": 0.8,
    })
    assert result["agent"] == "derivatives"
    assert result["signal"] in {"BUY", "SELL", "NEUTRAL", "HOLD"}
    assert "crowding" in " ".join(result["risk_flags"]).lower() or "risk" in " ".join(result["risk_flags"]).lower()


def test_macro_analyst_stays_conservative_for_short_horizon():
    result = MacroAnalyst().analyze({
        "dxy": 102.5,
        "treasury_yield_10y": 4.3,
        "cpi": 0.3,
        "fed_message": "hawkish",
        "horizon_hours": 4,
    })
    assert result["agent"] == "macro"
    assert result["signal"] in {"BUY", "SELL", "NEUTRAL", "HOLD"}


def test_trading_pipeline_synthesizes_safe_decision(bullish_snapshot):
    pipeline = TradingPipeline()
    result = pipeline.evaluate(
        market_snapshot=bullish_snapshot,
        account_equity=10000.0,
        onchain_metrics={
            "exchange_inflows": 4000,
            "exchange_outflows": 3200,
            "netflow": 800,
            "transfer_classification": "exchange_inflow",
            "whale_activity": "moderate",
        },
        news_events=[
            {"headline": "ETF inflows strong", "source": "official", "sentiment": 0.9, "impact": "HIGH_IMPACT"},
            {"headline": "whale accumulation rising", "source": "exchange", "sentiment": 0.7, "impact": "MEDIUM_IMPACT"},
        ],
        derivatives_metrics={
            "funding_rate": 0.0002,
            "open_interest": 3.1,
            "basis": 0.004,
            "crowding_score": 0.6,
            "liquidation_risk": 0.3,
        },
        macro_metrics={
            "dxy": 100.0,
            "fed_message": "neutral",
            "horizon_hours": 24,
        },
        entry=50000.0,
        stop=49000.0,
        target=54000.0,
        spread=0.0008,
        expected_slippage=0.001,
        liquidity=0.82,
        size=1000.0,
    )
    assert result["decision"] in {"BUY", "HOLD", "NO_TRADE"}
    assert "risk" in result["risk_summary"].lower() or result["execution"]["allowed"] is True


def test_provider_interfaces_return_data_unavailable():
    provider = MarketDataProvider()
    assert provider.fetch("BTC/USD") == DATA_UNAVAILABLE

    assert NewsProvider().fetch("BTC/USD") == DATA_UNAVAILABLE
    assert OnChainProvider().fetch("BTC/USD") == DATA_UNAVAILABLE
    assert DerivativesProvider().fetch("BTC/USD") == DATA_UNAVAILABLE
    assert MacroProvider().fetch("BTC/USD") == DATA_UNAVAILABLE
    assert ExchangeProvider().fetch("BTC/USD") == DATA_UNAVAILABLE


def test_fundamentals_analyst_bullish_growth_story():
    result = FundamentalsAnalyst().analyze({
        "earnings_growth": 25.0,
        "revenue_growth": 18.0,
        "pe_relative_to_sector": 1.1,
        "guidance": "raised",
        "insider_activity": "buying",
    })
    assert result["agent"] == "fundamentals"
    assert result["signal"] == "BUY"
    assert result["confidence"] >= 0.7


def test_fundamentals_analyst_rejects_unreliable_earnings():
    result = FundamentalsAnalyst().analyze({
        "earnings_growth": 500.0,  # absurd growth
        "revenue_growth": 5.0,
        "pe_relative_to_sector": 1.0,
        "guidance": "neutral",
        "insider_activity": "neutral",
    })
    assert result["signal"] == "NEUTRAL"
    assert "low_quality_data" in result["risk_flags"]


def test_asset_config_crypto_has_onchain_no_fundamentals():
    config = AssetConfig("crypto")
    assert config.has_onchain is True
    assert config.has_fundamentals is False
    assert "onchain" in config.get_applicable_agents()
    assert "fundamentals" not in config.get_applicable_agents()


def test_asset_config_equity_has_fundamentals_no_onchain():
    config = AssetConfig("equity")
    assert config.has_onchain is False
    assert config.has_fundamentals is True
    assert "fundamentals" in config.get_applicable_agents()
    assert "onchain" not in config.get_applicable_agents()


def test_paper_trading_backtest_calculates_metrics():
    backtest = PaperTradingBacktester(initial_capital=10000.0)
    trade1 = {"symbol": "BTC/USD", "entry": 50000.0, "side": "LONG", "size": 0.1}
    result1 = backtest.execute_trade(trade1, exit_price=51000.0, slippage_bps=1.0)
    assert result1.pnl > 0

    trade2 = {"symbol": "BTC/USD", "entry": 51000.0, "side": "LONG", "size": 0.1}
    result2 = backtest.execute_trade(trade2, exit_price=50500.0, slippage_bps=1.0)
    assert result2.pnl < 0

    metrics = backtest.get_metrics()
    assert metrics["total_trades"] == 2
    assert metrics["win_rate"] == 50.0
    assert metrics["profit_factor"] > 0


def test_baseline_comparison_identifies_outperformance():
    system_metrics = {"total_return_pct": 15.0, "max_drawdown": 2.0, "win_rate": 60.0, "profit_factor": 1.8}
    baseline_return = 8.0
    baseline_drawdown = 5.0

    result = BaselineComparison.compare(system_metrics, baseline_return, baseline_drawdown)
    assert result["outperformance"] > 0
    assert result["drawdown_improvement"] > 0
