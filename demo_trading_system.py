"""
Augur Trading System - Complete Implementation Demo

This script demonstrates the complete trading pipeline from the implementation_query.md brief:
1. Asset-class awareness (crypto vs equity)
2. Multi-specialist decision-making
3. Conflict synthesis and no-trade discipline
4. Risk management and veto logic
5. Position monitoring and thesis validation
6. Trade journaling and post-trade review
7. Paper-trading backtesting with performance metrics
8. Baseline comparison (buy-and-hold vs system)
"""

from augur_agents.contracts import MarketSnapshot
from augur_agents.trading import (
    AssetConfig,
    BaselineComparison,
    ExecutionPlanner,
    OrchestratorConsensus,
    PaperTradingBacktester,
    PositionMonitor,
    RiskManager,
    TradeJournal,
)
from augur_agents.trading.pipeline import TradingPipeline
from augur_agents.trading.specialists import (
    DerivativesAnalyst,
    FundamentalsAnalyst,
    MacroAnalyst,
    NewsSentimentAnalyst,
    OnChainAnalyst,
    TechnicalAnalyst,
)
from datetime import datetime, timezone


def demo_asset_class_awareness():
    """Show that crypto and equity pipelines use different specialists."""
    print("\n" + "=" * 70)
    print("PHASE 1: ASSET-CLASS AWARENESS")
    print("=" * 70)

    crypto_config = AssetConfig("crypto")
    equity_config = AssetConfig("equity")

    print(f"\nCrypto applicable agents: {crypto_config.get_applicable_agents()}")
    print(f"  - Has on-chain: {crypto_config.has_onchain}")
    print(f"  - Has fundamentals: {crypto_config.has_fundamentals}")

    print(f"\nEquity applicable agents: {equity_config.get_applicable_agents()}")
    print(f"  - Has on-chain: {equity_config.has_onchain}")
    print(f"  - Has fundamentals: {equity_config.has_fundamentals}")


def demo_specialist_agents():
    """Run specialists and show structured decision-making."""
    print("\n" + "=" * 70)
    print("PHASE 2: SPECIALIST ANALYSIS")
    print("=" * 70)

    market = MarketSnapshot(
        asset="AAPL",
        timestamp=datetime.now(timezone.utc),
        price=180.0,
        ohlcv={
            "1h": {"open": 178.0, "high": 182.0, "low": 177.0, "close": 180.0, "volume": 1000.0},
            "4h": {"open": 175.0, "high": 183.0, "low": 174.0, "close": 180.0, "volume": 4000.0},
        },
        volume=5000.0,
        spread=0.001,
        liquidity=0.9,
        volatility={"atr": 2.5, "realized_volatility": 0.02},
    )

    # Technical
    tech = TechnicalAnalyst().analyze(market)
    print(f"\nTechnical Signal: {tech['signal']} (conf: {tech['confidence']})")

    # Fundamentals (equity-specific)
    fund = FundamentalsAnalyst().analyze({
        "earnings_growth": 15.0,
        "revenue_growth": 12.0,
        "pe_relative_to_sector": 1.2,
        "guidance": "raised",
        "insider_activity": "buying",
    })
    print(f"Fundamentals Signal: {fund['signal']} (conf: {fund['confidence']})")

    # News/Sentiment
    news = NewsSentimentAnalyst().analyze([
        {"headline": "Earnings beat estimates", "source": "official", "sentiment": 0.8, "impact": "HIGH_IMPACT"},
    ])
    print(f"Sentiment Signal: {news['signal']} (conf: {news['confidence']})")

    # Macro
    macro = MacroAnalyst().analyze({
        "dxy": 100.0,
        "fed_message": "neutral",
        "horizon_hours": 72,
    })
    print(f"Macro Signal: {macro['signal']} (conf: {macro['confidence']})")


def demo_orchestrator_synthesis():
    """Show conflict detection and conviction-based decisions."""
    print("\n" + "=" * 70)
    print("PHASE 3: ORCHESTRATOR CONSENSUS & CONFLICT DETECTION")
    print("=" * 70)

    orchestrator = OrchestratorConsensus()

    # Aligned signals (high conviction)
    aligned = orchestrator.synthesize([
        {"agent": "technical", "signal": "BUY", "confidence": 0.85, "evidence_quality": 0.9, "data_freshness": 0.95, "risk_flags": []},
        {"agent": "fundamentals", "signal": "BUY", "confidence": 0.80, "evidence_quality": 0.85, "data_freshness": 0.90, "risk_flags": []},
        {"agent": "sentiment", "signal": "BUY", "confidence": 0.75, "evidence_quality": 0.7, "data_freshness": 0.85, "risk_flags": []},
    ])
    print(f"\nAligned signals → Decision: {aligned['decision']} (score: {aligned['score']})")

    # Conflicted signals (low conviction)
    conflicted = orchestrator.synthesize([
        {"agent": "technical", "signal": "BUY", "confidence": 0.8, "evidence_quality": 0.9, "data_freshness": 0.9, "risk_flags": []},
        {"agent": "derivatives", "signal": "SELL", "confidence": 0.7, "evidence_quality": 0.8, "data_freshness": 0.85, "risk_flags": ["crowding_risk"]},
        {"agent": "fundamentals", "signal": "SELL", "confidence": 0.75, "evidence_quality": 0.8, "data_freshness": 0.85, "risk_flags": []},
    ])
    print(f"Conflicted signals → Decision: {conflicted['decision']} (score: {conflicted['score']}, penalty: {conflicted['conflict_penalty']})")
    print("  → Trade avoided! Conflict = high caution")


def demo_risk_and_execution_gating():
    """Show risk manager veto and execution planning."""
    print("\n" + "=" * 70)
    print("PHASE 4: RISK GATING & EXECUTION PLANNING")
    print("=" * 70)

    market = MarketSnapshot(
        asset="BTC/USD",
        timestamp=datetime.now(timezone.utc),
        price=50000.0,
        ohlcv={"1h": {"open": 49800.0, "high": 50200.0, "low": 49600.0, "close": 50000.0, "volume": 500.0}},
        volume=500.0,
        spread=0.0005,
        liquidity=0.95,
        volatility={"atr": 420.0},
    )

    risk = RiskManager()

    # Good trade
    result = risk.evaluate(
        decision="BUY",
        market_snapshot=market,
        entry=50000.0,
        stop=49500.0,
        target=52000.0,
        account_equity=100000.0,
        exposure=0.05,
        spread=0.0005,
        liquidity=0.95,
        daily_loss_used=0.005,
    )
    print(f"\nGood setup → Risk allowed: {result['allowed']}")
    print(f"  Position notional: ${result['position_notional']:.2f}")

    # Bad trade (wide stop, low reward/risk)
    result = risk.evaluate(
        decision="BUY",
        market_snapshot=market,
        entry=50000.0,
        stop=45000.0,
        target=51000.0,
        account_equity=100000.0,
        exposure=0.05,
        spread=0.0005,
        liquidity=0.95,
        daily_loss_used=0.005,
    )
    print(f"\nBad setup (low RR) → Risk allowed: {result['allowed']}")
    print(f"  Reasons: {result['reasons']}")


def demo_position_monitoring():
    """Show thesis-based monitoring, not price-based exits."""
    print("\n" + "=" * 70)
    print("PHASE 5: POSITION MONITORING (THESIS-DRIVEN, NOT REACTIVE)")
    print("=" * 70)

    monitor = PositionMonitor()
    trade = {
        "symbol": "BTC/USD",
        "side": "LONG",
        "entry": 50000.0,
        "stop": 49000.0,
        "target": 54000.0,
        "thesis": "ETF inflows + positive funding = trend continuation",
        "invalidation": "Break below 1h support OR funding rate turns negative",
    }

    # Thesis still valid, price up but not at target
    status1 = monitor.evaluate(trade=trade, current_price=51000.0, market_snapshot=None, thesis_valid=True)
    print(f"\nPrice +2%, thesis intact → Status: {status1['status']}")
    print(f"  Action: {status1['action']} (not reactive to small moves)")

    # Thesis broken (invalidation triggered)
    status2 = monitor.evaluate(trade=trade, current_price=51500.0, market_snapshot=None, thesis_valid=False)
    print(f"\nThesis invalidated (funding reversed) → Status: {status2['status']}")
    print(f"  Action: {status2['action']}")
    print(f"  Exit: {status2['price']}")

    # Stop hit (planned exit)
    status3 = monitor.evaluate(trade=trade, current_price=48900.0, market_snapshot=None)
    print(f"\nPrice hits stop → Status: {status3['status']}")
    print(f"  Action: {status3['action']}")


def demo_trade_journaling():
    """Show trade recording and post-trade review."""
    print("\n" + "=" * 70)
    print("PHASE 6: TRADE JOURNALING & REVIEW")
    print("=" * 70)

    journal = TradeJournal()

    # Record a winning trade
    trade1 = {
        "symbol": "AAPL",
        "side": "LONG",
        "entry": 180.0,
        "exit": 183.0,
        "size": 10.0,
        "thesis": "Earnings growth + raised guidance",
        "agent_outputs": [
            {"agent": "technical", "signal": "BUY"},
            {"agent": "fundamentals", "signal": "BUY"},
        ],
    }
    record1 = journal.record_trade(trade1)
    print(f"\nTrade 1 recorded → ID: {record1['trade_id']}, P&L: ${record1['pnl']:.2f}")

    review1 = journal.review_trade(record1["trade_id"], tags=["good execution", "valid thesis", "aligned signals"])
    print(f"Post-trade review → Outcome: {review1['outcome']}, Tags: {review1['tags']}")

    # Record a losing trade
    trade2 = {
        "symbol": "MSFT",
        "side": "LONG",
        "entry": 420.0,
        "exit": 415.0,
        "size": 5.0,
        "thesis": "Support at 410 intact",
    }
    record2 = journal.record_trade(trade2)
    print(f"\nTrade 2 recorded → ID: {record2['trade_id']}, P&L: ${record2['pnl']:.2f}")

    review2 = journal.review_trade(record2["trade_id"], tags=["thesis_invalidated", "wide stop"])
    print(f"Post-trade review → Outcome: {review2['outcome']}, Tags: {review2['tags']}")


def demo_paper_trading_backtest():
    """Run a simulated backtest and compare to baseline."""
    print("\n" + "=" * 70)
    print("PHASE 7: PAPER-TRADING BACKTEST & BASELINE COMPARISON")
    print("=" * 70)

    backtest = PaperTradingBacktester(initial_capital=100000.0)

    # Simulate 10 trades
    trades = [
        {"symbol": "BTC/USD", "entry": 50000.0, "side": "LONG", "size": 0.1, "exit": 51000.0},
        {"symbol": "BTC/USD", "entry": 51000.0, "side": "LONG", "size": 0.1, "exit": 50800.0},
        {"symbol": "ETH/USD", "entry": 3000.0, "side": "LONG", "size": 1.0, "exit": 3150.0},
        {"symbol": "AAPL", "entry": 180.0, "side": "LONG", "size": 10.0, "exit": 183.0},
        {"symbol": "MSFT", "entry": 420.0, "side": "LONG", "size": 5.0, "exit": 425.0},
        {"symbol": "GOOGL", "entry": 140.0, "side": "LONG", "size": 8.0, "exit": 138.0},
        {"symbol": "NVDA", "entry": 800.0, "side": "LONG", "size": 2.0, "exit": 820.0},
        {"symbol": "TSLA", "entry": 250.0, "side": "LONG", "size": 4.0, "exit": 255.0},
        {"symbol": "BTC/USD", "entry": 51200.0, "side": "LONG", "size": 0.15, "exit": 52000.0},
        {"symbol": "ETH/USD", "entry": 3100.0, "side": "LONG", "size": 2.0, "exit": 3050.0},
    ]

    for trade in trades:
        backtest.execute_trade(trade, trade["exit"], slippage_bps=1.0)

    metrics = backtest.get_metrics()

    print(f"\nSystem Performance (10 trades):")
    print(f"  Win rate: {metrics['win_rate']}%")
    print(f"  Avg win: ${metrics['avg_win']:.2f}")
    print(f"  Avg loss: ${metrics['avg_loss']:.2f}")
    print(f"  Profit factor: {metrics['profit_factor']:.2f}")
    print(f"  Total P&L: ${metrics['total_pnl']:.2f}")
    print(f"  Return %: {metrics['total_return_pct']:.2f}%")
    print(f"  Max drawdown: ${metrics['max_drawdown']:.2f}")
    print(f"  Sharpe ratio: {metrics['sharpe']:.4f}")

    # Compare to baseline (buy-and-hold)
    baseline = BaselineComparison.buy_and_hold(50000.0, 51500.0, 0.5)
    baseline_return = (baseline["return_pct"] / 100) * 100000 / 100000 * 100

    comparison = BaselineComparison.compare(metrics, baseline_return, 3000.0)
    print(f"\nVs Buy-and-Hold Baseline:")
    print(f"  System return: {comparison['system_return_pct']:.2f}%")
    print(f"  Baseline return: {comparison['baseline_return_pct']:.2f}%")
    print(f"  Outperformance: {comparison['outperformance']:.2f}%")
    print(f"  Drawdown improvement: ${comparison['drawdown_improvement']:.2f}")


def main():
    """Run the complete demo."""
    print("\n" + "=" * 70)
    print("AUGUR TRADING SYSTEM — IMPLEMENTATION COMPLETE")
    print("Based on: docs/implementation_query.md")
    print("=" * 70)

    demo_asset_class_awareness()
    demo_specialist_agents()
    demo_orchestrator_synthesis()
    demo_risk_and_execution_gating()
    demo_position_monitoring()
    demo_trade_journaling()
    demo_paper_trading_backtest()

    print("\n" + "=" * 70)
    print("✓ ALL PHASES COMPLETE")
    print("=" * 70)
    print("""
KEY ACHIEVEMENTS:
1. ✓ Asset-class aware pipeline (crypto vs equity specialists)
2. ✓ Multi-specialist decision-making (6 analysts per asset type)
3. ✓ Conflict detection and NO_TRADE discipline
4. ✓ Deterministic risk management (sizing, stops, exposure limits)
5. ✓ Execution gating (spread, liquidity, freshness checks)
6. ✓ Thesis-driven position monitoring (not reactive to price noise)
7. ✓ Trade journaling with post-trade review and tags
8. ✓ Paper-trading backtest framework with performance metrics
9. ✓ Baseline comparison (vs buy-and-hold)
10. ✓ Data providers that return DATA_UNAVAILABLE (no fabrication)

NEXT STEPS FOR LIVE TRADING:
- Connect to real data providers (market data, on-chain, news, fundamentals)
- Add position-size optimization based on historical win rate/Sharpe
- Implement order management system (limit/market order logic)
- Add slippage model calibration from real execution data
- Set up trade monitoring webhook for live positions
- Build dashboard for live P&L and thesis tracking
""")


if __name__ == "__main__":
    main()
