"""Price data loading.

For development we use synthetic prices (a random walk with drift). Because the
data is random, NO strategy has a real edge on it -- so any strategy that shows
amazing results is, by construction, cheating somehow. That makes it perfect
for testing the auditor.

Real market data comes later. Only add a dataset to this repo if its license
allows public redistribution (the repo is public).
"""
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def synthetic_prices(
    n_days: int = 2520,
    annual_drift: float = 0.07,
    annual_vol: float = 0.18,
    start_price: float = 100.0,
    seed: int = 7,
    start: str = "2015-01-02",
) -> pd.DataFrame:
    """Geometric-Brownian-motion daily closes. Returns a DataFrame with a 'close' column."""
    rng = np.random.default_rng(seed)
    dt = 1 / TRADING_DAYS
    log_ret = rng.normal((annual_drift - 0.5 * annual_vol**2) * dt, annual_vol * np.sqrt(dt), n_days)
    close = start_price * np.exp(np.cumsum(log_ret))
    idx = pd.bdate_range(start, periods=n_days)
    return pd.DataFrame({"close": close}, index=idx)
