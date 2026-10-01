"""Honest: classic 50/200-day moving-average crossover, long-only, correctly shifted."""
import pandas as pd

NAME = "honest"
DESCRIPTION = "50/200-day moving-average crossover, long when fast > slow."
PLANTED_BUG = None
N_TRIALS = 1
PARAM_GRID = None


def positions_for(prices: pd.DataFrame, fast: int = 50, slow: int = 200) -> pd.Series:
    c = prices["close"]
    signal = (c.rolling(fast).mean() > c.rolling(slow).mean()).astype(float)
    return signal.shift(1).fillna(0.0)  # decided at close t-1, held during day t


def run(prices: pd.DataFrame) -> pd.Series:
    return positions_for(prices, 50, 200)
