"""The backtest loop.

TIMING CONVENTION (the most important rule in this repo):
    positions[t] is the exposure held from close[t-1] to close[t].
    It earns the return close[t] / close[t-1] - 1.
    Therefore positions[t] may only use information available at close[t-1].

A strategy that computes a signal from close[t] must shift it by one bar
before returning it as positions. Forgetting that shift = lookahead bias.
The engine deliberately does NOT shift for you -- that's where real user
bugs live, and it's what the auditor is built to catch.
"""
from dataclasses import dataclass

import pandas as pd

from engine.metrics import summarize


@dataclass
class BacktestResult:
    returns: pd.Series   # daily strategy returns
    equity: pd.Series    # equity curve starting from 1.0
    metrics: dict


def run_backtest(prices: pd.DataFrame, positions: pd.Series, cost_bps: float = 1.0) -> BacktestResult:
    close = prices["close"]
    asset_ret = close.pct_change().fillna(0.0)
    pos = positions.reindex(close.index).fillna(0.0).clip(-1.0, 1.0)
    turnover = pos.diff().abs().fillna(pos.abs())
    strat = pos * asset_ret - turnover * cost_bps / 1e4
    equity = (1 + strat).cumprod()
    exposure = float((pos != 0).mean())  # share of days with a position; a "fix" that never trades is no fix
    return BacktestResult(returns=strat, equity=equity, metrics={**summarize(strat), "exposure": exposure})
