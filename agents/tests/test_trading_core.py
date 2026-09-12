from __future__ import annotations

import pytest

from augur_agents.contracts import MarketSnapshot
from augur_agents.trading.execution import ExecutionPlanner
from augur_agents.trading.journal import TradeJournal
from augur_agents.trading.monitor import PositionMonitor
from augur_agents.trading.orchestrator import OrchestratorConsensus
from augur_agents.trading.risk import RiskManager


@pytest.fixture
def market_snapshot():
    return MarketSnapshot(
        asset="BTC/USD",
        timestamp=__import__("datetime").datetime.now(__import__("datetime").timezone.utc),
        price=50000.0,
        ohlcv={
            "15m": {"open": 49700.0, "high": 50200.0, "low": 49600.0, "close": 50000.0, "volume": 12.0},
            "1h": {"open": 49500.0, "high": 50300.0, "low": 49400.0, "close": 50000.0, "volume": 40.0},
            "4h": {"open": 49000.0, "high": 50600.0, "low": 48800.0, "close": 50000.0, "volume": 120.0},
            "1d": {"open": 47000.0, "high": 51000.0, "low": 46500.0, "close": 50000.0, "volume": 350.0},
        },
        volume=120.0,
        spread=0.0005,
        liquidity=0.8,
        volatility={"atr": 500.0, "realized_volatility": 0.04},
        derivatives={"funding_rate": 0.0001, "open_interest": 2.5, "basis": 0.002, "liquidation_data": {"shorts": 500, "longs": 450}},
    )


def test_position_size_formula():
    assert RiskManager().position_notional(account_equity=10000, risk_fraction=0.005, stop_distance_fraction=0.05) == pytest.approx(1000.0)


def test_risk_manager_rejects_bad_trade(market_snapshot):
    risk = RiskManager()
    result = risk.evaluate(
        decision="BUY",
        market_snapshot=market_snapshot,
        entry=50000.0,
        stop=49000.0,
        target=53000.0,
        account_equity=10000.0,
        exposure=0.12,
        spread=0.003,
        liquidity=0.2,
        daily_loss_used=0.015,
    )
    assert result["allowed"] is False
    assert result["reasons"]


def test_orchestrator_reduces_conflict_to_no_trade():
    consensus = OrchestratorConsensus()
    decision = consensus.synthesize([
        {"agent": "technical", "signal": "BUY", "confidence": 0.8, "evidence_quality": 0.9, "data_freshness": 0.9, "timeframe": "4h", "risk_flags": []},
        {"agent": "onchain", "signal": "SELL", "confidence": 0.7, "evidence_quality": 0.7, "data_freshness": 0.8, "timeframe": "1d", "risk_flags": ["crowded"]},
        {"agent": "derivatives", "signal": "SELL", "confidence": 0.75, "evidence_quality": 0.8, "data_freshness": 0.85, "timeframe": "1h", "risk_flags": ["crowded"]},
        {"agent": "news", "signal": "NEUTRAL", "confidence": 0.5, "evidence_quality": 0.5, "data_freshness": 0.7, "timeframe": "4h", "risk_flags": []},
    ])
    assert decision["decision"] in {"NO_TRADE", "HOLD"}
    assert decision["score"] < 0.3 or decision["conflict_penalty"] > 0


def test_execution_planner_rejects_stale_or_illiquid_trade(market_snapshot):
    planner = ExecutionPlanner()
    plan = planner.plan(
        decision="BUY",
        market_snapshot=market_snapshot,
        spread=0.005,
        expected_slippage=0.003,
        liquidity=0.05,
        size=2000.0,
        stop=49000.0,
        signal_age_seconds=30,
    )
    assert plan["allowed"] is False


def test_position_monitor_detects_thesis_break_and_stop_hit(market_snapshot):
    monitor = PositionMonitor()
    trade = {
        "symbol": "BTC/USD",
        "side": "LONG",
        "entry": 50000.0,
        "stop": 49000.0,
        "target": 54000.0,
        "thesis": "ETF inflows and price structure remain constructive",
        "invalidation": "break below 1h support or funding turns hostile",
    }

    stop_hit = monitor.evaluate(trade=trade, current_price=48900.0, market_snapshot=market_snapshot, volatility_spike=False, news_impact="medium")
    assert stop_hit["status"] == "HIT_STOP"

    thesis_broken = monitor.evaluate(
        trade=trade,
        current_price=50200.0,
        market_snapshot=market_snapshot,
        volatility_spike=False,
        news_impact="high",
        thesis_valid=False,
    )
    assert thesis_broken["status"] == "THESIS_INVALIDATED"


def test_trade_journal_records_outcome_and_review_tags():
    journal = TradeJournal()
    trade = {
        "symbol": "BTC/USD",
        "side": "LONG",
        "entry": 50000.0,
        "exit": 51000.0,
        "size": 1.0,
        "thesis": "trend continuation",
        "agent_outputs": [{"agent": "technical", "signal": "BUY"}],
    }

    record = journal.record_trade(trade)
    review = journal.review_trade(record["trade_id"], tags=["good execution", "valid thesis"])

    assert record["pnl"] == 1000.0
    assert review["tags"] == ["good execution", "valid thesis"]
    assert review["outcome"] == "profitable"

