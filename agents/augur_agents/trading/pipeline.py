"""End-to-end trading pipeline that composes specialists, risk, and execution."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .calibration import SpecialistCalibrator
from .execution import ExecutionPlanner
from .guard import TradingGuard
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
    """Deterministic pipeline for converting market data into a safe trade decision.

    Position size always comes from the risk engine, never from the caller.
    When a calibrator has enough consensus history, the trade must also show a
    positive Kelly edge at its calibrated win probability, and the risk budget
    is scaled to a fraction of that Kelly bet (meta-labeling).
    """

    def __init__(
        self,
        *,
        risk: RiskManager | None = None,
        execution: ExecutionPlanner | None = None,
        calibrator: SpecialistCalibrator | None = None,
        guard: TradingGuard | None = None,
        kelly_multiplier: float = 0.25,
    ) -> None:
        self.risk = risk or RiskManager()
        self.execution = execution or ExecutionPlanner()
        self.calibrator = calibrator
        self.orchestrator = OrchestratorConsensus(calibrator=calibrator)
        self.guard = guard or TradingGuard()
        self.kelly_multiplier = kelly_multiplier

    def evaluate(
        self,
        *,
        market_snapshot: Any,
        account_equity: float,
        exposure: float,
        daily_loss_used: float,
        spread: float,
        expected_slippage: float,
        liquidity: float,
        onchain_metrics: dict[str, Any] | None = None,
        news_events: list[dict[str, Any]] | None = None,
        derivatives_metrics: dict[str, Any] | None = None,
        macro_metrics: dict[str, Any] | None = None,
        entry: float | None = None,
        stop: float | None = None,
        target: float | None = None,
        portfolio_exposure: float | None = None,
        correlated_exposure: float = 0.0,
        signal_age_seconds: float = 5.0,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        """`exposure`, `portfolio_exposure`, `correlated_exposure` and
        `daily_loss_used` are fractions of equity read from the live account.
        `stop` and `target` default to ATR multiples around `entry`."""
        technical = TechnicalAnalyst(
            stop_atr_multiple=self.risk.stop_atr_multiple,
            target_atr_multiple=self.risk.target_atr_multiple,
        ).analyze(market_snapshot)
        onchain = OnChainAnalyst().analyze(onchain_metrics or {})
        news = NewsSentimentAnalyst().analyze(news_events or [])
        derivatives = DerivativesAnalyst().analyze(derivatives_metrics or {})
        macro = MacroAnalyst().analyze(macro_metrics or {})

        outputs = [technical, onchain, news, derivatives, macro]
        consensus = self.orchestrator.synthesize(outputs)
        decision = consensus["decision"]
        vetoes: list[str] = []

        entry = entry if entry is not None else float(getattr(market_snapshot, "price", 0.0) or 0.0)
        if decision in {"BUY", "SELL"} and (stop is None or target is None):
            atr = float((getattr(market_snapshot, "volatility", None) or {}).get("atr", 0.0) or 0.0)
            if entry > 0 and atr > 0:
                levels = RiskManager.bracket_levels(
                    entry=entry,
                    atr=atr,
                    side=decision,
                    stop_multiple=self.risk.stop_atr_multiple,
                    target_multiple=self.risk.target_atr_multiple,
                )
                stop = levels["stop"] if stop is None else stop
                target = levels["target"] if target is None else target
            else:
                vetoes.append("no ATR available to place volatility-scaled stop and target")
        stop = stop or 0.0
        target = target or 0.0

        risk_fraction = None
        win_probability = consensus.get("win_probability")
        if decision in {"BUY", "SELL"} and win_probability is not None and entry > 0 and stop > 0 and stop != entry:
            reward_risk = abs(target - entry) / abs(entry - stop)
            kelly = RiskManager.kelly_fraction(win_probability=win_probability, reward_risk=reward_risk)
            if kelly <= 0:
                vetoes.append("no positive edge at the calibrated win probability")
            else:
                risk_fraction = min(self.risk.max_risk_per_trade, self.kelly_multiplier * kelly)

        if decision in {"BUY", "SELL"}:
            vetoes.extend(self.guard.check(now))

        risk_eval = self.risk.evaluate(
            decision=decision,
            market_snapshot=market_snapshot,
            entry=entry,
            stop=stop,
            target=target,
            account_equity=account_equity,
            exposure=exposure,
            spread=spread,
            liquidity=liquidity,
            daily_loss_used=daily_loss_used,
            risk_fraction=risk_fraction,
            portfolio_exposure=portfolio_exposure,
            correlated_exposure=correlated_exposure,
        )

        execution = self.execution.plan(
            decision=decision,
            market_snapshot=market_snapshot,
            spread=spread,
            expected_slippage=expected_slippage,
            liquidity=liquidity,
            size=risk_eval["position_qty"],
            stop=stop,
            target=target,
            signal_age_seconds=signal_age_seconds,
        )

        final_decision = decision
        if vetoes or not risk_eval["allowed"] or not execution["allowed"]:
            final_decision = "NO_TRADE"

        order = None
        if final_decision in {"BUY", "SELL"}:
            # Counts approved entries; the caller must submit `order` as one bracketed request.
            self.guard.record_entry(now)
            order = {
                "side": final_decision,
                "order_type": execution["order_type"],
                "quantity": risk_eval["position_qty"],
                "notional": risk_eval["position_notional"],
                "entry": entry,
                "stop_loss": stop,
                "take_profit": target,
            }

        risk_summary = "; ".join(risk_eval["reasons"]) if risk_eval["reasons"] else "no risk vetoes"

        return {
            "decision": final_decision,
            "consensus": consensus,
            "risk_summary": risk_summary,
            "vetoes": vetoes,
            "risk": risk_eval,
            "execution": execution,
            "order": order,
            "specialists": {
                "technical": technical,
                "onchain": onchain,
                "news": news,
                "derivatives": derivatives,
                "macro": macro,
            },
        }
