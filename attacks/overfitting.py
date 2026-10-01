"""Overfitting tests: walk-forward validation and the deflated Sharpe ratio.

Deflated Sharpe ratio (Bailey & Lopez de Prado, 2014): the probability that
the strategy's true Sharpe is above zero AFTER accounting for how many
configurations were tried. Try 280 things and the best one will look good by
luck; the DSR discounts for that.
"""
import math
from statistics import NormalDist

import numpy as np
import pandas as pd

from attacks.base import AttackResult
from engine.backtest import run_backtest
from engine.metrics import sharpe

EULER_GAMMA = 0.5772156649015329
_N = NormalDist()


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """Expected best per-period Sharpe among n_trials strategies with zero true skill."""
    if n_trials <= 1 or var_sr <= 0:
        return 0.0
    return math.sqrt(var_sr) * ((1 - EULER_GAMMA) * _N.inv_cdf(1 - 1 / n_trials)
                                + EULER_GAMMA * _N.inv_cdf(1 - 1 / (n_trials * math.e)))


def deflated_sharpe_ratio(returns: pd.Series, n_trials: int, var_sr: float) -> tuple[float, float]:
    """Returns (DSR probability, SR0 benchmark). Uses per-period (not annualized) Sharpe."""
    r = returns.dropna()
    sd = r.std(ddof=1)
    if len(r) < 3 or sd == 0:
        return 0.0, 0.0
    sr = r.mean() / sd
    skew, kurt = r.skew(), r.kurt() + 3.0          # pandas kurt() is excess kurtosis
    sr0 = expected_max_sharpe(n_trials, var_sr)
    denom = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr**2))
    return _N.cdf((sr - sr0) * math.sqrt(len(r) - 1) / denom), sr0


def _per_period_sharpe(returns: pd.Series) -> float:
    sd = returns.std(ddof=1)
    return 0.0 if sd == 0 else float(returns.mean() / sd)


def deflated_sharpe_test(strategy, prices: pd.DataFrame) -> AttackResult:
    returns = run_backtest(prices, strategy.run(prices)).returns
    grid = getattr(strategy, "PARAM_GRID", None)
    n_trials = int(getattr(strategy, "N_TRIALS", 1) or 1)
    var_sr = 0.0
    if grid and hasattr(strategy, "positions_for"):
        trial_srs = [_per_period_sharpe(run_backtest(prices, strategy.positions_for(prices, **p)).returns) for p in grid]
        var_sr = float(np.var(trial_srs, ddof=1))
        n_trials = len(grid)
    dsr, sr0 = deflated_sharpe_ratio(returns, n_trials, var_sr)
    metrics = {"dsr": dsr, "n_trials": n_trials, "sharpe_annual": sharpe(returns),
               "luck_benchmark_sharpe_annual": sr0 * math.sqrt(252)}
    if n_trials > 1 and dsr < 0.5:
        return AttackResult("deflated_sharpe", "FAIL",
                            f"After accounting for {n_trials} configurations tried, there's only a {dsr:.0%} chance "
                            "the edge is real -- the best of that many random tries would look this good by luck.", metrics)
    if dsr < 0.95:
        return AttackResult("deflated_sharpe", "WARN",
                            f"Confidence the edge is real is {dsr:.0%} (below 95%): results aren't statistically "
                            "significant yet.", metrics)
    return AttackResult("deflated_sharpe", "PASS", f"{dsr:.0%} confidence the edge is real after adjusting for trials.", metrics)


def walk_forward_test(strategy, prices: pd.DataFrame, split: float = 0.6) -> AttackResult:
    """Pick the best config on the first part of history, then test it on the unseen rest."""
    grid = getattr(strategy, "PARAM_GRID", None)
    if not grid or not hasattr(strategy, "positions_for"):
        return AttackResult("walk_forward", "N/A", "No parameter search declared, so there's nothing to walk forward.")
    cut = prices.index[int(len(prices) * split)]
    is_mask, oos_mask = prices.index < cut, prices.index >= cut

    def split_sharpes(p):
        r = run_backtest(prices, strategy.positions_for(prices, **p)).returns
        return sharpe(r[is_mask]), sharpe(r[oos_mask])

    scored = [(split_sharpes(p), p) for p in grid]
    (is_sr, oos_sr), best = max(scored, key=lambda x: x[0][0])
    metrics = {"in_sample_sharpe": is_sr, "out_of_sample_sharpe": oos_sr, "chosen_params": best,
               "split_date": str(cut.date())}
    if is_sr > 0.5 and oos_sr < 0.5 * is_sr:
        return AttackResult("walk_forward", "FAIL",
                            f"The best configuration on past data (Sharpe {is_sr:.2f}) fell to {oos_sr:.2f} on data "
                            "it hadn't seen: the edge doesn't survive out of sample.", metrics)
    if oos_sr < 0.75 * is_sr:
        return AttackResult("walk_forward", "WARN",
                            f"Out-of-sample Sharpe ({oos_sr:.2f}) is well below in-sample ({is_sr:.2f}).", metrics)
    return AttackResult("walk_forward", "PASS", f"Held up out of sample (Sharpe {is_sr:.2f} -> {oos_sr:.2f}).", metrics)
