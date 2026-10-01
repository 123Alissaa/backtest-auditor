"""Broken (lookahead): trend filter that forgets to shift its signal.

The signal is computed from today's close and used to trade today's return --
information you couldn't have had when the position was taken.
"""
import pandas as pd

NAME = "lookahead"
DESCRIPTION = "Long when price is above its 20-day average, otherwise in cash."
PLANTED_BUG = "lookahead"
N_TRIALS = 1
PARAM_GRID = None


def run(prices: pd.DataFrame, window: int = 20) -> pd.Series:
    c = prices["close"]
    sma = c.rolling(window).mean()
    signal = (c > sma).astype(float)
    signal[sma.isna()] = 0.0
    return signal  # BUG: missing .shift(1) -- uses today's close to trade today's return
