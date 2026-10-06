"""Honest: classic 14-day RSI mean reversion, every input from the past only."""
import pandas as pd

NAME = "honest_rsi"
DESCRIPTION = "RSI mean reversion: long while the 14-day RSI is below 40 (oversold)."
PLANTED_BUG = None
N_TRIALS = 1
PARAM_GRID = None


def run(prices: pd.DataFrame, period: int = 14, entry: float = 40.0) -> pd.Series:
    c = prices["close"]
    delta = c.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rsi = 100 - 100 / (1 + gain / loss)
    signal = (rsi < entry).astype(float)
    return signal.shift(1).fillna(0.0)  # decided at yesterday's close, held today
