"""Sample strategies used for development, tests, and the demo.

Every strategy module exposes:
    NAME, DESCRIPTION
    run(prices) -> pd.Series        the full pipeline exactly as the author runs it
    N_TRIALS                        how many configurations the author tried (1 if none)
    PARAM_GRID (optional)           list of param dicts the author searched over
    positions_for(prices, **params) (optional) positions for one configuration
    PLANTED_BUG                     ground truth for OUR tests only -- the auditor must never read it

Classic bugs: lookahead, leaky, overfit. Real-world mistakes: next_day (shift(-1)
"alignment"), weekly (weekly signal back-filled onto days), zscore (full-history
normalization). Honest: honest (SMA crossover), honest_rsi.
"""
from strategies import (honest_rsi, honest_sma, leaky_smoother, lookahead_momentum, next_day_return, overfit_grid,
                        weekly_trend, zscore_price)

STRATEGIES = {m.NAME: m for m in (honest_sma, lookahead_momentum, leaky_smoother, overfit_grid,
                                  next_day_return, weekly_trend, zscore_price, honest_rsi)}
