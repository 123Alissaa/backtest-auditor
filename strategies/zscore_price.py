"""Broken (leakage): mean reversion against the price's average, standardized with
statistics of the WHOLE price history -- including years that haven't happened yet.
A very common "normalize your features" step done on the full dataset.
"""
import pandas as pd

NAME = "zscore"
DESCRIPTION = "Mean reversion: buy when the price is cheap relative to its normal range (z-score)."
PLANTED_BUG = "leakage"
N_TRIALS = 1
PARAM_GRID = None


def run(prices: pd.DataFrame, entry: float = -0.5) -> pd.Series:
    c = prices["close"]
    z = (c - c.mean()) / c.std()  # BUG: full-history mean/std includes the future
    signal = (z < entry).astype(float)
    return signal.shift(1).fillna(0.0)
