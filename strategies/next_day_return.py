"""Broken (lookahead): "aligns" returns with shift(-1), a frequent pandas slip,
so the momentum feature quietly contains tomorrow's return.
"""
import pandas as pd

NAME = "next_day"
DESCRIPTION = "Short-term momentum: long when the last 5 daily returns average above zero."
PLANTED_BUG = "lookahead"
N_TRIALS = 1
PARAM_GRID = None


def run(prices: pd.DataFrame, window: int = 5) -> pd.Series:
    c = prices["close"]
    ret = c.pct_change().shift(-1)  # BUG: shift(-1) pulls tomorrow's return onto today
    momentum = ret.rolling(window).mean()
    signal = (momentum > 0).astype(float)
    return signal.shift(1).fillna(0.0)
