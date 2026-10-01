"""Broken (data leakage): trend-follows a CENTERED moving average.

The author correctly shifts the final signal -- but the feature itself leaks:
rolling(..., center=True) averages 10 days into the future. A one-bar shift
test won't catch this; a point-in-time test will.
"""
import numpy as np
import pandas as pd

NAME = "leaky"
DESCRIPTION = "Trend-following on a smoothed 21-day price trend."
PLANTED_BUG = "leakage"
N_TRIALS = 1
PARAM_GRID = None


def run(prices: pd.DataFrame, window: int = 21) -> pd.Series:
    c = prices["close"]
    smooth = c.rolling(window, center=True).mean()  # BUG: centered window uses future prices
    trend = np.sign(smooth.diff())
    return trend.shift(1).fillna(0.0)  # shift looks responsible, but the leak is upstream
