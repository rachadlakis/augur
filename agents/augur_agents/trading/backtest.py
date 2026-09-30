"""Paper trading simulation and performance metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any


def simulate_bracket_exit(
    *, side: str, stop: float, target: float, bars: list[dict[str, float]]
) -> tuple[float, str, int]:
    """Walk OHLC bars after entry and return (exit_price, reason, bar_index).

    Conservative by construction: a bar that opens through the stop fills at
    the open (gap slippage); a bar whose range touches both stop and target is
    assumed to hit the stop first, since intrabar order is unknown. With no
    exit, the position closes at the last bar's close ("time_exit").
    """
    if not bars:
        raise ValueError("need at least one bar after entry")
    is_long = side in {"LONG", "BUY"}
    for index, bar in enumerate(bars):
        open_, high, low = float(bar["open"]), float(bar["high"]), float(bar["low"])
        if is_long:
            if open_ <= stop:
                return open_, "stop_gap", index
            if open_ >= target:
                return open_, "target_gap", index
            if low <= stop:
                return stop, "stop", index
            if high >= target:
                return target, "target", index
        else:
            if open_ >= stop:
                return open_, "stop_gap", index
            if open_ <= target:
                return open_, "target_gap", index
            if high >= stop:
                return stop, "stop", index
            if low <= target:
                return target, "target", index
    return float(bars[-1]["close"]), "time_exit", len(bars) - 1


@dataclass
class TradeResult:
    symbol: str
    entry: float
    exit: float
    size: float
    side: str
    pnl: float
    return_pct: float
    slippage_cost: float
    fee_cost: float = 0.0
    funding_cost: float = 0.0


class PaperTradingBacktester:
    """Simulate the trading system against historical data.

    Costs are charged on both legs: slippage moves each fill against the trade,
    and a taker fee is paid on each side's notional. The default fee is the
    standard Binance spot taker rate (10 bps); set it per venue. Only 1 of 19
    closed-loop LLM trading studies modeled costs, and cost-free backtests are
    the main source of false positives.

    Metrics are computed on an equity curve. Call `mark()` to record
    mark-to-market equity between trades (e.g. once per day) so drawdown
    includes open-position losses and Sharpe is computed on daily returns.
    """

    def __init__(self, initial_capital: float = 100000.0, *, fee_bps: float = 10.0, periods_per_year: int = 252) -> None:
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.fee_bps = fee_bps
        self.periods_per_year = periods_per_year
        self.trades: list[TradeResult] = []
        self.daily_pnl: dict[str, float] = {}
        self._equity_curve: list[tuple[datetime | None, float]] = [(None, initial_capital)]

    def execute_trade(
        self,
        trade: dict[str, Any],
        exit_price: float,
        slippage_bps: float = 5.0,
        *,
        funding_rate: float = 0.0,
        funding_periods: int = 0,
        exit_time: datetime | None = None,
    ) -> TradeResult:
        """Close a round trip. `funding_rate` is per period; longs pay positive funding."""
        entry = float(trade.get("entry", 0.0) or 0.0)
        size = float(trade.get("size", 0.0) or 0.0)
        side = trade.get("side", "LONG")
        is_long = side in {"LONG", "BUY"}
        if entry <= 0 or size <= 0:
            raise ValueError("trade entry and size must be positive")

        # Both fills move against the trade.
        slip = slippage_bps / 10000
        fill_entry = entry * (1 + slip) if is_long else entry * (1 - slip)
        fill_exit = exit_price * (1 - slip) if is_long else exit_price * (1 + slip)
        slippage_cost = (abs(fill_entry - entry) + abs(fill_exit - exit_price)) * size

        fee_cost = (fill_entry + fill_exit) * size * (self.fee_bps / 10000)
        funding_cost = entry * size * funding_rate * funding_periods * (1 if is_long else -1)

        gross = (fill_exit - fill_entry) * size if is_long else (fill_entry - fill_exit) * size
        pnl = gross - fee_cost - funding_cost
        return_pct = pnl / (entry * size) * 100

        result = TradeResult(
            symbol=trade.get("symbol", "UNKNOWN"),
            entry=fill_entry,
            exit=fill_exit,
            size=size,
            side=side,
            pnl=pnl,
            return_pct=return_pct,
            slippage_cost=slippage_cost,
            fee_cost=fee_cost,
            funding_cost=funding_cost,
        )

        self.capital += pnl
        self.trades.append(result)
        self._equity_curve.append((exit_time, self.capital))
        if exit_time is not None:
            key = exit_time.date().isoformat()
            self.daily_pnl[key] = self.daily_pnl.get(key, 0.0) + pnl
        return result

    def execute_bracket(
        self,
        trade: dict[str, Any],
        bars: list[dict[str, float]],
        slippage_bps: float = 5.0,
        *,
        exit_time: datetime | None = None,
    ) -> tuple[TradeResult, str]:
        """Resolve a bracketed trade (`stop`, `target` in `trade`) against the bars that followed."""
        exit_price, reason, _ = simulate_bracket_exit(
            side=trade.get("side", "LONG"), stop=float(trade["stop"]), target=float(trade["target"]), bars=bars
        )
        return self.execute_trade(trade, exit_price, slippage_bps, exit_time=exit_time), reason

    def mark(self, equity: float, timestamp: datetime | None = None) -> None:
        """Record mark-to-market equity (realized capital plus open-position P&L)."""
        self._equity_curve.append((timestamp, equity))

    @property
    def equity_curve(self) -> list[tuple[datetime | None, float]]:
        return list(self._equity_curve)

    def _period_returns(self) -> tuple[list[float], str]:
        points = self._equity_curve[1:]
        timed = [(ts, equity) for ts, equity in points if ts is not None]
        if points and len(timed) == len(points):
            closes: dict[date, float] = {}
            for ts, equity in timed:
                closes[ts.date()] = equity  # last mark of each day
            series = [self.initial_capital] + [closes[d] for d in sorted(closes)]
            basis = "daily"
        else:
            series = [equity for _, equity in self._equity_curve]
            basis = "per_trade"
        returns = [b / a - 1.0 for a, b in zip(series, series[1:]) if a > 0]
        return returns, basis

    def get_metrics(self) -> dict[str, Any]:
        if not self.trades:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "payoff_ratio": 0.0,
                "total_pnl": 0.0,
                "total_return_pct": 0.0,
                "max_drawdown": 0.0,
                "max_drawdown_usd": 0.0,
                "sharpe": 0.0,
                "sharpe_basis": "none",
                "total_fees": 0.0,
                "total_slippage": 0.0,
                "total_funding": 0.0,
            }

        winning = [t for t in self.trades if t.pnl > 0]
        losing = [t for t in self.trades if t.pnl < 0]
        total_pnl = sum(t.pnl for t in self.trades)
        total_return_pct = (self.capital - self.initial_capital) / self.initial_capital * 100

        gross_profit = sum(t.pnl for t in winning)
        gross_loss = abs(sum(t.pnl for t in losing))
        avg_win = gross_profit / len(winning) if winning else 0.0
        avg_loss = gross_loss / len(losing) if losing else 0.0
        if gross_loss > 0:
            profit_factor = gross_profit / gross_loss
        else:
            profit_factor = math.inf if gross_profit > 0 else 0.0
        payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0
        win_rate = len(winning) / len(self.trades) * 100

        peak = -math.inf
        max_dd_pct = 0.0
        max_dd_usd = 0.0
        for _, equity in self._equity_curve:
            peak = max(peak, equity)
            max_dd_usd = max(max_dd_usd, peak - equity)
            if peak > 0:
                max_dd_pct = max(max_dd_pct, (peak - equity) / peak * 100)

        returns, basis = self._period_returns()
        sharpe = 0.0
        if len(returns) >= 2:
            mean = sum(returns) / len(returns)
            std = math.sqrt(sum((r - mean) ** 2 for r in returns) / (len(returns) - 1))
            if std > 0:
                sharpe = mean / std
                # Annualize only when periods are real calendar days.
                if basis == "daily":
                    sharpe *= math.sqrt(self.periods_per_year)

        return {
            "total_trades": len(self.trades),
            "win_rate": round(win_rate, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": profit_factor if math.isinf(profit_factor) else round(profit_factor, 4),
            "payoff_ratio": round(payoff_ratio, 4),
            "total_pnl": round(total_pnl, 2),
            "total_return_pct": round(total_return_pct, 2),
            "max_drawdown": round(max_dd_pct, 2),
            "max_drawdown_usd": round(max_dd_usd, 2),
            "sharpe": round(sharpe, 4),
            "sharpe_basis": basis,
            "total_fees": round(sum(t.fee_cost for t in self.trades), 2),
            "total_slippage": round(sum(t.slippage_cost for t in self.trades), 2),
            "total_funding": round(sum(t.funding_cost for t in self.trades), 2),
        }


class BaselineComparison:
    """Compare system performance to buy-and-hold baseline."""

    @staticmethod
    def buy_and_hold(entry: float, exit: float, size: float) -> dict[str, Any]:
        pnl = (exit - entry) * size
        return_pct = (exit - entry) / entry * 100
        return {"strategy": "buy_and_hold", "pnl": pnl, "return_pct": return_pct}

    @staticmethod
    def simple_moving_average_crossover(prices: list[float], fast_period: int = 10, slow_period: int = 20) -> list[str]:
        """Generate simple signals based on MA crossover."""
        signals = []
        if len(prices) < slow_period:
            return ["HOLD"] * len(prices)

        for i in range(len(prices)):
            # Both windows need full history; a shorter slice would wrap to the end of the list.
            if i < slow_period:
                signals.append("HOLD")
            else:
                fast_ma = sum(prices[i - fast_period : i]) / fast_period
                slow_ma = sum(prices[i - slow_period : i]) / slow_period
                if fast_ma > slow_ma:
                    signals.append("BUY")
                elif fast_ma < slow_ma:
                    signals.append("SELL")
                else:
                    signals.append("HOLD")

        return signals

    @staticmethod
    def compare(
        system_metrics: dict[str, Any],
        baseline_return_pct: float,
        baseline_drawdown: float,
    ) -> dict[str, Any]:
        """Drawdowns are percentages of peak equity, as `get_metrics()` reports them."""
        system_return = system_metrics.get("total_return_pct", 0.0)
        system_drawdown = system_metrics.get("max_drawdown", 0.0)

        return {
            "system_return_pct": system_return, ## pct is the percentage return of the system
            "baseline_return_pct": baseline_return_pct, ## pct is the percentage return of the baseline
            "outperformance": round(system_return - baseline_return_pct, 2),
            "system_drawdown": system_drawdown,
            "baseline_drawdown": baseline_drawdown,
            "drawdown_improvement": round(baseline_drawdown - system_drawdown, 2),
            "win_rate": system_metrics.get("win_rate", 0.0),
            "profit_factor": system_metrics.get("profit_factor", 0.0),
        }
