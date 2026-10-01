"""Point-in-time test: does position[t] change if we hide the future?

For a sample of dates t we re-run the strategy on data truncated at t, with
close[t] itself nudged up and down. position[t] may only use data through
close[t-1], so an honest strategy returns the SAME position[t] every time.
If it changes, the strategy is using information it couldn't have had:
lookahead, a leaky feature (e.g. a centered window), or parameters chosen
on the full history.

This catches leaks the signal-shift test misses.
"""
import numpy as np
import pandas as pd

from attacks.base import AttackResult


def _same(a, b) -> bool:
    a = 0.0 if pd.isna(a) else float(a)
    b = 0.0 if pd.isna(b) else float(b)
    return np.isclose(a, b)


def point_in_time_test(run, prices: pd.DataFrame, n_checks: int = 12, bump: float = 0.05,
                       min_history: int = 300, seed: int = 0) -> AttackResult:
    full = run(prices)
    rng = np.random.default_rng(seed)
    candidates = np.arange(min_history, len(prices) - 1)
    checks = np.sort(rng.choice(candidates, size=min(n_checks, len(candidates)), replace=False))
    col = prices.columns.get_loc("close")

    violations = []
    for i in checks:
        t = prices.index[i]
        for factor in (1 - bump, 1 + bump):
            trunc = prices.iloc[: i + 1].copy()
            trunc.iloc[-1, col] *= factor
            if not _same(run(trunc).iloc[-1], full.loc[t]):
                violations.append(str(t.date()))
                break  # one mismatch is enough for this date

    rate = len(violations) / len(checks)
    metrics = {"dates_checked": int(len(checks)), "violations": len(violations),
               "violation_rate": rate, "example_dates": violations[:5]}
    if violations:
        return AttackResult("point_in_time", "FAIL",
                            f"On {len(violations)} of {len(checks)} dates, the position changed when future data was "
                            "hidden: the strategy uses information that wasn't available at decision time.", metrics)
    return AttackResult("point_in_time", "PASS",
                        f"Positions were identical with the future hidden on all {len(checks)} dates checked.", metrics)
