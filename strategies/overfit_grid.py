"""Broken (overfitting): searches ~280 configurations (moving-average windows x
which weekdays to trade) on the FULL history and reports the best one.

Each individual configuration is timed correctly -- the problem is picking the
winner after seeing all the data. "Only trade Mondays and Thursdays" is the
kind of rule that looks brilliant in-sample and means nothing.
"""
from itertools import combinations

import pandas as pd

from engine.backtest import run_backtest

NAME = "overfit"
DESCRIPTION = "Optimized moving-average crossover with a weekday filter (best of ~280 configs)."
PLANTED_BUG = "overfitting"

_WEEKDAY_SETS = [days for r in range(1, 6) for days in combinations(range(5), r)]
PARAM_GRID = [
    {"fast": f, "slow": s, "days": days}
    for f in (5, 10, 20)
    for s in (50, 100, 200)
    for days in _WEEKDAY_SETS
]
N_TRIALS = len(PARAM_GRID)


def positions_for(prices: pd.DataFrame, fast: int, slow: int, days: tuple) -> pd.Series:
    c = prices["close"]
    trend_up = (c.rolling(fast).mean() > c.rolling(slow).mean()).astype(float)
    pos = trend_up.shift(1).fillna(0.0)                   # timing is correct
    return pos * prices.index.dayofweek.isin(days)        # weekday filter (known at the open)


def best_params(prices: pd.DataFrame) -> dict:
    return max(PARAM_GRID, key=lambda p: run_backtest(prices, positions_for(prices, **p)).metrics["sharpe"])


def run(prices: pd.DataFrame) -> pd.Series:
    return positions_for(prices, **best_params(prices))  # BUG: winner picked using the whole sample
