"""Deterministic risk controls for trading decisions."""

from __future__ import annotations

from typing import Any


class RiskManager:
    """Mandatory veto for candidate trades.

    This class is intentionally deterministic: the LLM may reason about a trade,
    but it cannot change the arithmetic that protects the account. This keeps the
    safety policy enforceable even when the agent layer is noisy.
    """

    def __init__(
        self,
        *,
        max_risk_per_trade: float = 0.005,
        max_daily_loss: float = 0.02,
        max_asset_exposure: float = 0.10,
        max_portfolio_exposure: float = 0.20,
        max_correlated_exposure: float = 0.20,
        min_reward_risk: float = 1.5,
        min_liquidity: float = 0.15,
        max_spread: float = 0.003,
    ) -> None:
        self.max_risk_per_trade = max_risk_per_trade
        self.max_daily_loss = max_daily_loss
        self.max_asset_exposure = max_asset_exposure
        self.max_portfolio_exposure = max_portfolio_exposure
        self.max_correlated_exposure = max_correlated_exposure
        self.min_reward_risk = min_reward_risk
        self.min_liquidity = min_liquidity
        self.max_spread = max_spread

    @staticmethod
    def position_notional(*, account_equity: float, risk_fraction: float, stop_distance_fraction: float) -> float:
        if account_equity <= 0 or risk_fraction <= 0 or stop_distance_fraction <= 0:
            raise ValueError("position_notional requires positive inputs")
        return account_equity * risk_fraction / stop_distance_fraction

    def evaluate(
        self,
        *,
        decision: str,
        market_snapshot: Any,
        entry: float,
        stop: float,
        target: float,
        account_equity: float,
        exposure: float,
        spread: float,
        liquidity: float,
        daily_loss_used: float,
        risk_fraction: float | None = None,
    ) -> dict[str, Any]:
        reasons: list[str] = []
        if decision not in {"BUY", "SELL", "HOLD", "NO_TRADE"}:
            reasons.append("unknown decision")

        if decision in {"BUY", "SELL"}:
            if entry <= 0 or stop <= 0:
                reasons.append("entry and stop must be positive")

            if target <= 0:
                reasons.append("target must be positive")

            if risk_fraction is None:
                risk_fraction = self.max_risk_per_trade

            stop_distance_fraction = abs(entry - stop) / entry
            if stop_distance_fraction <= 0:
                reasons.append("invalid stop distance")

            notional = self.position_notional(
                account_equity=account_equity,
                risk_fraction=risk_fraction,
                stop_distance_fraction=stop_distance_fraction,
            )
            if exposure > self.max_asset_exposure:
                reasons.append("asset exposure exceeds configured maximum")
            if exposure > self.max_portfolio_exposure:
                reasons.append("portfolio exposure exceeds configured maximum")
            if daily_loss_used >= self.max_daily_loss:
                reasons.append("daily loss limit reached")
            if liquidity < self.min_liquidity:
                reasons.append("liquidity below minimum threshold")
            if spread > self.max_spread:
                reasons.append("spread exceeds configured maximum")
            if notional <= 0:
                reasons.append("position size is non-positive")

            if entry > 0 and stop > 0 and target > 0:
                risk_per_unit = abs(entry - stop)
                reward_per_unit = abs(target - entry)
                if risk_per_unit <= 0:
                    reasons.append("reward/risk is undefined when the stop is at the entry")
                else:
                    rr = reward_per_unit / risk_per_unit
                    if rr < self.min_reward_risk:
                        reasons.append("reward/risk below configured minimum")

        if decision == "NO_TRADE":
            return {"allowed": False, "reasons": ["no trade selected"], "position_notional": 0.0}

        return {
            "allowed": not reasons,
            "reasons": reasons,
            "position_notional": self.position_notional(
                account_equity=account_equity,
                risk_fraction=risk_fraction if risk_fraction is not None else self.max_risk_per_trade,
                stop_distance_fraction=max(abs(entry - stop) / entry, 1e-9),
            ) if decision in {"BUY", "SELL"} and entry > 0 and stop > 0 else 0.0,
        }
