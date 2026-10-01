"""Performance metrics. All functions take DAILY strategy returns or an equity curve."""
import numpy as np
import pandas as pd

from engine.data import TRADING_DAYS


def sharpe(returns: pd.Series, periods: int = TRADING_DAYS) -> float:
    """Annualized Sharpe ratio (risk-free rate assumed 0)."""
    sd = returns.std(ddof=1)
    if not np.isfinite(sd) or sd == 0:
        return 0.0
    return float(returns.mean() / sd * np.sqrt(periods))


def cagr(equity: pd.Series, periods: int = TRADING_DAYS) -> float:
    """Compound annual growth rate of an equity curve that starts near 1.0."""
    years = len(equity) / periods
    if years <= 0 or equity.iloc[-1] <= 0:
        return float("nan")
    return float(equity.iloc[-1] ** (1 / years) - 1)


def max_drawdown(equity: pd.Series) -> float:
    """Worst peak-to-trough drop, as a negative fraction (e.g. -0.35 = -35%)."""
    return float((equity / equity.cummax() - 1).min())


def summarize(returns: pd.Series) -> dict:
    equity = (1 + returns).cumprod()
    return {
        "cagr": cagr(equity),
        "sharpe": sharpe(returns),
        "max_drawdown": max_drawdown(equity),
        "total_return": float(equity.iloc[-1] - 1),
    }
