"""Broken (lookahead): computes a weekly trend, then maps it back to daily bars
with method="bfill" -- so Monday already trades on Friday's close.
No simple pattern rule flags this; the deterministic tests have to.
"""
import pandas as pd

NAME = "weekly"
DESCRIPTION = "Weekly trend filter: long when the weekly close is above its 4-week average."
PLANTED_BUG = "lookahead"
N_TRIALS = 1
PARAM_GRID = None


def run(prices: pd.DataFrame, weeks: int = 4) -> pd.Series:
    c = prices["close"]
    weekly = c.resample("W-FRI").last()
    trend = (weekly > weekly.rolling(weeks).mean()).astype(float)
    daily = trend.reindex(c.index, method="bfill")  # BUG: each day gets the END of its week
    return daily.shift(1).fillna(0.0)
