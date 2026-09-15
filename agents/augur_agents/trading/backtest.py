"""Paper trading simulation and performance metrics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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


class PaperTradingBacktester:
    """Simulate the trading system against historical data."""

    def __init__(self, initial_capital: float = 100000.0) -> None:
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.trades: list[TradeResult] = []
        self.daily_pnl: dict[str, float] = {}

    def execute_trade(
        self, trade: dict[str, Any], exit_price: float, slippage_bps: float = 1.0
    ) -> TradeResult:
        entry = float(trade.get("entry", 0.0) or 0.0)
        size = float(trade.get("size", 0.0) or 0.0)
        side = trade.get("side", "LONG")

        # Account for slippage
        slippage = (entry * size) * (slippage_bps / 10000)
        effective_exit = exit_price - (slippage / size) if side == "LONG" else exit_price + (slippage / size)

        pnl = (effective_exit - entry) * size if side == "LONG" else (entry - effective_exit) * size
        return_pct = ((effective_exit - entry) / entry * 100) if side == "LONG" else ((entry - effective_exit) / entry * 100)

        result = TradeResult(
            symbol=trade.get("symbol", "UNKNOWN"),
            entry=entry,
            exit=effective_exit,
            size=size,
            side=side,
            pnl=pnl,
            return_pct=return_pct,
            slippage_cost=slippage,
        )

        self.capital += pnl
        self.trades.append(result)
        return result

    def get_metrics(self) -> dict[str, float]:
        if not self.trades:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "total_pnl": 0.0,
                "total_return_pct": 0.0,
                "max_drawdown": 0.0,
                "sharpe": 0.0,
            }

        winning = [t for t in self.trades if t.pnl > 0]
        losing = [t for t in self.trades if t.pnl < 0]
        total_pnl = sum(t.pnl for t in self.trades)
        total_return_pct = (self.capital - self.initial_capital) / self.initial_capital * 100

        avg_win = sum(t.pnl for t in winning) / len(winning) if winning else 0.0
        avg_loss = abs(sum(t.pnl for t in losing) / len(losing)) if losing else 0.0
        profit_factor = avg_win / avg_loss if avg_loss > 0 else 0.0
        win_rate = len(winning) / len(self.trades) * 100 if self.trades else 0.0

        # Simple max drawdown calculation
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        for trade in self.trades:
            cumulative += trade.pnl
            peak = max(peak, cumulative)
            dd = peak - cumulative
            max_dd = max(max_dd, dd)

        return {
            "total_trades": len(self.trades),
            "win_rate": round(win_rate, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 4),
            "total_pnl": round(total_pnl, 2),
            "total_return_pct": round(total_return_pct, 2),
            "max_drawdown": round(max_dd, 2),
            "sharpe": round(total_return_pct / max(1, len(self.trades)) * (252 ** 0.5) if len(self.trades) > 0 else 0, 4),
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
            if i < fast_period:
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
