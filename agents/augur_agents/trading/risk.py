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
        stop_atr_multiple: float = 2.0,
        target_atr_multiple: float = 4.0,
    ) -> None:
        self.max_risk_per_trade = max_risk_per_trade
        self.max_daily_loss = max_daily_loss
        self.max_asset_exposure = max_asset_exposure
        self.max_portfolio_exposure = max_portfolio_exposure
        self.max_correlated_exposure = max_correlated_exposure
        self.min_reward_risk = min_reward_risk
        self.min_liquidity = min_liquidity
        self.max_spread = max_spread
        self.stop_atr_multiple = stop_atr_multiple
        self.target_atr_multiple = target_atr_multiple

    @staticmethod
    def position_notional(*, account_equity: float, risk_fraction: float, stop_distance_fraction: float) -> float:
        if account_equity <= 0 or risk_fraction <= 0 or stop_distance_fraction <= 0:
            raise ValueError("position_notional requires positive inputs")
        return account_equity * risk_fraction / stop_distance_fraction

    @staticmethod
    def bracket_levels(
        *, entry: float, atr: float, side: str, stop_multiple: float = 2.0, target_multiple: float = 4.0
    ) -> dict[str, float]:
        """Stop and target placed in ATR units so they widen with volatility.

        Because size = equity * risk / stop distance, an ATR stop makes notional
        shrink as volatility grows. Fixed-percentage stops are volatility-blind,
        the largest loss source in production LLM trading fleets.
        """
        if entry <= 0 or atr <= 0:
            raise ValueError("bracket_levels requires a positive entry and ATR")
        direction = 1.0 if side.upper() in {"BUY", "LONG"} else -1.0
        return {
            "stop": entry - direction * stop_multiple * atr,
            "target": entry + direction * target_multiple * atr,
        }

    @staticmethod
    def kelly_fraction(*, win_probability: float, reward_risk: float) -> float:
        """Kelly-optimal fraction of equity to risk on a binary bet; <= 0 means no edge."""
        if reward_risk <= 0:
            return 0.0
        return win_probability - (1.0 - win_probability) / reward_risk

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
        portfolio_exposure: float | None = None,
        correlated_exposure: float = 0.0,
    ) -> dict[str, Any]:
        """Veto or size a candidate trade.

        `exposure` is this asset's current notional as a fraction of equity,
        `portfolio_exposure` the whole book's (defaults to `exposure`), and
        `correlated_exposure` the book's exposure to assets correlated with this
        one. The new position is capped to the remaining headroom under every
        limit rather than assumed to fit.
        """
        reasons: list[str] = []
        if decision not in {"BUY", "SELL", "HOLD", "NO_TRADE"}:
            reasons.append("unknown decision")

        if decision == "NO_TRADE":
            return {"allowed": False, "reasons": ["no trade selected"], "position_notional": 0.0, "position_qty": 0.0}

        if decision not in {"BUY", "SELL"}:
            return {"allowed": not reasons, "reasons": reasons, "position_notional": 0.0, "position_qty": 0.0}

        if portfolio_exposure is None:
            portfolio_exposure = exposure
        if risk_fraction is None:
            risk_fraction = self.max_risk_per_trade
        risk_fraction = min(risk_fraction, self.max_risk_per_trade)

        if entry <= 0 or stop <= 0:
            reasons.append("entry and stop must be positive")
        if target <= 0:
            reasons.append("target must be positive")
        if account_equity <= 0:
            reasons.append("account equity must be positive")
        if risk_fraction <= 0:
            reasons.append("risk fraction must be positive")

        is_long = decision == "BUY"
        if entry > 0 and stop > 0 and target > 0:
            if is_long and not (stop < entry < target):
                reasons.append("long trade requires stop < entry < target")
            if not is_long and not (target < entry < stop):
                reasons.append("short trade requires target < entry < stop")

        if exposure >= self.max_asset_exposure:
            reasons.append("asset exposure exceeds configured maximum")
        if portfolio_exposure >= self.max_portfolio_exposure:
            reasons.append("portfolio exposure exceeds configured maximum")
        if correlated_exposure >= self.max_correlated_exposure:
            reasons.append("correlated exposure exceeds configured maximum")
        if daily_loss_used >= self.max_daily_loss:
            reasons.append("daily loss limit reached")
        if liquidity < self.min_liquidity:
            reasons.append("liquidity below minimum threshold")
        if spread > self.max_spread:
            reasons.append("spread exceeds configured maximum")

        notional = 0.0
        if entry > 0 and stop > 0 and target > 0 and stop != entry:
            risk_per_unit = abs(entry - stop)
            reward_per_unit = abs(target - entry)
            if reward_per_unit / risk_per_unit < self.min_reward_risk:
                reasons.append("reward/risk below configured minimum")

            if account_equity > 0 and risk_fraction > 0:
                notional = self.position_notional(
                    account_equity=account_equity,
                    risk_fraction=risk_fraction,
                    stop_distance_fraction=risk_per_unit / entry,
                )
                headroom = min(
                    self.max_asset_exposure - exposure,
                    self.max_portfolio_exposure - portfolio_exposure,
                    self.max_correlated_exposure - correlated_exposure,
                )
                notional = max(0.0, min(notional, headroom * account_equity))
        elif entry > 0 and stop == entry:
            reasons.append("reward/risk is undefined when the stop is at the entry")

        if not reasons and notional <= 0:
            reasons.append("position size is non-positive")

        allowed = not reasons
        return {
            "allowed": allowed,
            "reasons": reasons,
            "position_notional": notional if allowed else 0.0,
            "position_qty": notional / entry if allowed and entry > 0 else 0.0,
        }
