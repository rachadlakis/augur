"""End-to-end trading pipeline that composes specialists, risk, and execution."""

from __future__ import annotations

from typing import Any

from .execution import ExecutionPlanner
from .orchestrator import OrchestratorConsensus
from .risk import RiskManager
from .specialists import (
    DerivativesAnalyst,
    MacroAnalyst,
    NewsSentimentAnalyst,
    OnChainAnalyst,
    TechnicalAnalyst,
)


class TradingPipeline:
    """Deterministic pipeline for converting market data into a safe trade decision."""

    def __init__(self) -> None:
        self.risk = RiskManager()
        self.execution = ExecutionPlanner()
        self.orchestrator = OrchestratorConsensus()

    def evaluate(
        self,
        *,
        market_snapshot: Any,
        account_equity: float,
        onchain_metrics: dict[str, Any] | None = None,
        news_events: list[dict[str, Any]] | None = None,
        derivatives_metrics: dict[str, Any] | None = None,
        macro_metrics: dict[str, Any] | None = None,
        entry: float,
        stop: float,
        target: float,
        spread: float,
        expected_slippage: float,
        liquidity: float,
        size: float,
        signal_age_seconds: float = 5.0,
    ) -> dict[str, Any]:
        technical = TechnicalAnalyst().analyze(market_snapshot)
        onchain = OnChainAnalyst().analyze(onchain_metrics or {})
        news = NewsSentimentAnalyst().analyze(news_events or [])
        derivatives = DerivativesAnalyst().analyze(derivatives_metrics or {})
        macro = MacroAnalyst().analyze(macro_metrics or {})

        outputs = [technical, onchain, news, derivatives, macro]
        consensus = self.orchestrator.synthesize(outputs)

        risk_eval = self.risk.evaluate(
            decision=consensus["decision"],
            market_snapshot=market_snapshot,
            entry=entry,
            stop=stop,
            target=target,
            account_equity=account_equity,
            exposure=0.10,
            spread=spread,
            liquidity=liquidity,
            daily_loss_used=0.01,
        )

        execution = self.execution.plan(
            decision=consensus["decision"],
            market_snapshot=market_snapshot,
            spread=spread,
            expected_slippage=expected_slippage,
            liquidity=liquidity,
            size=size,
            stop=stop,
            signal_age_seconds=signal_age_seconds,
        )

        final_decision = consensus["decision"]
        if not risk_eval["allowed"] or not execution["allowed"]:
            final_decision = "NO_TRADE"

        risk_summary = "; ".join(risk_eval["reasons"]) if risk_eval["reasons"] else "no risk vetoes"

        return {
            "decision": final_decision,
            "consensus": consensus,
            "risk_summary": risk_summary,
            "execution": execution,
            "specialists": {
                "technical": technical,
                "onchain": onchain,
                "news": news,
                "derivatives": derivatives,
                "macro": macro,
            },
        }
