"""Statistics for deciding whether a strategy has an edge or just got lucky.

Implements the checks that separate real edges from backtest artifacts:
Probabilistic and Deflated Sharpe ratios (Bailey & Lopez de Prado), minimum
track-record length, benchmark alpha/beta so market exposure is not mistaken
for skill, day-clustered confidence intervals, a permutation test against a
null arm, and embargoed walk-forward splits. Stdlib-only.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from collections.abc import Hashable, Iterator
from statistics import NormalDist
from typing import Any

_NORMAL = NormalDist()
_EULER_GAMMA = 0.5772156649015329


def _moments(returns: list[float]) -> tuple[float, float, float, float]:
    """Mean, sample std, skewness, and (non-excess) kurtosis."""
    n = len(returns)
    mean = sum(returns) / n
    var = sum((r - mean) ** 2 for r in returns) / (n - 1)
    std = math.sqrt(var)
    if std == 0:
        return mean, 0.0, 0.0, 3.0
    pop_std = math.sqrt(sum((r - mean) ** 2 for r in returns) / n)
    skew = sum(((r - mean) / pop_std) ** 3 for r in returns) / n
    kurt = sum(((r - mean) / pop_std) ** 4 for r in returns) / n
    return mean, std, skew, kurt


def sharpe_ratio(returns: list[float]) -> float:
    """Per-period (non-annualized) Sharpe ratio."""
    if len(returns) < 2:
        return 0.0
    mean, std, _, _ = _moments(returns)
    return mean / std if std > 0 else 0.0


def probabilistic_sharpe_ratio(returns: list[float], benchmark_sharpe: float = 0.0) -> float:
    """Probability the true per-period Sharpe exceeds `benchmark_sharpe`,
    corrected for sample length, skew and fat tails."""
    n = len(returns)
    if n < 3:
        return 0.0
    _, std, skew, kurt = _moments(returns)
    if std == 0:
        return 0.0
    sr = sharpe_ratio(returns)
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr**2
    if denom <= 0:
        return 0.0
    return _NORMAL.cdf((sr - benchmark_sharpe) * math.sqrt(n - 1) / math.sqrt(denom))


def expected_max_sharpe(n_trials: int, sharpe_variance: float) -> float:
    """Sharpe the best of `n_trials` unskilled strategies would show by luck alone."""
    if n_trials < 2 or sharpe_variance <= 0:
        return 0.0
    return math.sqrt(sharpe_variance) * (
        (1 - _EULER_GAMMA) * _NORMAL.inv_cdf(1 - 1 / n_trials)
        + _EULER_GAMMA * _NORMAL.inv_cdf(1 - 1 / (n_trials * math.e))
    )


def deflated_sharpe_ratio(returns: list[float], *, n_trials: int, sharpe_variance: float) -> float:
    """PSR against the luck threshold implied by how many variants were tried.

    `sharpe_variance` is the variance of per-period Sharpe ratios across all
    `n_trials` configurations tested. Values above 0.95 are the usual bar.
    """
    return probabilistic_sharpe_ratio(returns, expected_max_sharpe(n_trials, sharpe_variance))


def min_track_record_years(annual_sharpe: float, *, t_stat: float = 2.0) -> float:
    """Years of daily data needed for `annual_sharpe` to reach `t_stat` (t ~ SR * sqrt(years))."""
    if annual_sharpe <= 0:
        return math.inf
    return (t_stat / annual_sharpe) ** 2


def alpha_beta(
    strategy_returns: list[float], benchmark_returns: list[float], *, periods_per_year: int = 252
) -> dict[str, float]:
    """OLS of strategy on benchmark returns: return you'd get from beta vs from skill."""
    n = len(strategy_returns)
    if n != len(benchmark_returns):
        raise ValueError("return series must be the same length")
    if n < 3:
        raise ValueError("need at least 3 periods")
    mean_x = sum(benchmark_returns) / n
    mean_y = sum(strategy_returns) / n
    sxx = sum((x - mean_x) ** 2 for x in benchmark_returns)
    if sxx == 0:
        raise ValueError("benchmark returns have zero variance")
    sxy = sum((x - mean_x) * (y - mean_y) for x, y in zip(benchmark_returns, strategy_returns))
    beta = sxy / sxx
    alpha = mean_y - beta * mean_x
    residuals = [y - alpha - beta * x for x, y in zip(benchmark_returns, strategy_returns)]
    s2 = sum(e**2 for e in residuals) / (n - 2)
    alpha_se = math.sqrt(s2 * (1 / n + mean_x**2 / sxx))
    return {
        "alpha_per_period": alpha,
        "alpha_annualized": alpha * periods_per_year,
        "alpha_t_stat": alpha / alpha_se if alpha_se > 0 else 0.0,
        "beta": beta,
    }


def day_clustered_mean(
    observations: list[tuple[Hashable, float]], *, confidence: float = 0.90
) -> dict[str, Any]:
    """Mean and CI with the market day as the inferential unit.

    Trades on the same day share the tape, so position-level intervals are too
    narrow (~2.5x in one production record). Values are averaged within each
    day, then across days. Uses a normal quantile, so treat intervals from fewer
    than ~30 days as optimistic.
    """
    by_day: dict[Hashable, list[float]] = defaultdict(list)
    for day, value in observations:
        by_day[day].append(value)
    day_means = [sum(v) / len(v) for v in by_day.values()]
    n = len(day_means)
    if n < 2:
        raise ValueError("need observations from at least 2 days")
    mean = sum(day_means) / n
    std = math.sqrt(sum((m - mean) ** 2 for m in day_means) / (n - 1))
    half_width = _NORMAL.inv_cdf(0.5 + confidence / 2) * std / math.sqrt(n)
    return {"mean": mean, "lower": mean - half_width, "upper": mean + half_width, "n_days": n}


def permutation_p_value(
    treatment: list[float], control: list[float], *, n_permutations: int = 10000, seed: int = 0
) -> float:
    """Two-sided p-value that treatment and control (e.g. a null arm) share a mean."""
    if not treatment or not control:
        raise ValueError("both arms need observations")
    observed = abs(sum(treatment) / len(treatment) - sum(control) / len(control))
    pooled = list(treatment) + list(control)
    k = len(treatment)
    rng = random.Random(seed)
    extreme = 0
    for _ in range(n_permutations):
        rng.shuffle(pooled)
        diff = abs(sum(pooled[:k]) / k - sum(pooled[k:]) / (len(pooled) - k))
        if diff >= observed - 1e-12:
            extreme += 1
    return (extreme + 1) / (n_permutations + 1)


def walk_forward_splits(
    n_samples: int, *, train_size: int, test_size: int, embargo: int = 0, step: int | None = None
) -> Iterator[tuple[range, range]]:
    """Chronological (train, test) index ranges; never random folds.

    `embargo` drops samples between train and test so labels that span the
    boundary (e.g. multi-day holding periods) cannot leak.
    """
    if train_size <= 0 or test_size <= 0 or embargo < 0:
        raise ValueError("train_size and test_size must be positive and embargo non-negative")
    step = step or test_size
    start = 0
    while start + train_size + embargo + test_size <= n_samples:
        train_end = start + train_size
        test_start = train_end + embargo
        yield range(start, train_end), range(test_start, test_start + test_size)
        start += step
