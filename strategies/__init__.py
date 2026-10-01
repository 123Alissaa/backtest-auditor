"""Sample strategies used for development, tests, and the demo.

Every strategy module exposes:
    NAME, DESCRIPTION
    run(prices) -> pd.Series        the full pipeline exactly as the author runs it
    N_TRIALS                        how many configurations the author tried (1 if none)
    PARAM_GRID (optional)           list of param dicts the author searched over
    positions_for(prices, **params) (optional) positions for one configuration
    PLANTED_BUG                     ground truth for OUR tests only -- the auditor must never read it

Three strategies are intentionally broken; one is honest.
"""
from strategies import honest_sma, leaky_smoother, lookahead_momentum, overfit_grid

STRATEGIES = {m.NAME: m for m in (honest_sma, lookahead_momentum, leaky_smoother, overfit_grid)}
