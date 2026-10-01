import numpy as np
import pandas as pd

from engine.backtest import run_backtest
from engine.data import synthetic_prices


def test_always_long_matches_buy_and_hold():
    p = synthetic_prices(n_days=300, seed=1)
    res = run_backtest(p, pd.Series(1.0, index=p.index), cost_bps=0.0)
    expected = p["close"].iloc[-1] / p["close"].iloc[0]
    assert np.isclose(res.equity.iloc[-1], expected)


def test_position_earns_the_return_of_its_own_day_only():
    idx = pd.bdate_range("2020-01-01", periods=4)
    p = pd.DataFrame({"close": [100.0, 110.0, 99.0, 99.0]}, index=idx)
    pos = pd.Series([0.0, 0.0, 1.0, 0.0], index=idx)       # held from close[1] to close[2]
    res = run_backtest(p, pos, cost_bps=0.0)
    assert np.isclose(res.returns.iloc[2], 99 / 110 - 1)
    assert res.returns.iloc[1] == 0.0 and res.returns.iloc[3] == 0.0


def test_costs_are_charged_on_turnover():
    p = synthetic_prices(n_days=50, seed=2)
    flat = pd.Series(0.0, index=p.index)
    flip = flat.copy(); flip.iloc[10] = 1.0
    res = run_backtest(p, flip, cost_bps=10.0)
    free = run_backtest(p, flip, cost_bps=0.0)
    assert np.isclose(free.returns.sum() - res.returns.sum(), 2 * 10 / 1e4)  # in and out
