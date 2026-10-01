"""Signal-shift test: delay every position by one extra bar and re-run.

An honest strategy barely changes -- one day of delay doesn't matter much.
A strategy that peeks at the future collapses, because the peek is gone.
"""
import pandas as pd

from attacks.base import AttackResult
from engine.backtest import run_backtest


def signal_shift_test(run, prices: pd.DataFrame, lag: int = 1) -> AttackResult:
    pos = run(prices)
    base = run_backtest(prices, pos)
    shifted = run_backtest(prices, pos.shift(lag).fillna(0.0))
    s0, s1 = base.metrics["sharpe"], shifted.metrics["sharpe"]
    drop = s0 - s1
    metrics = {
        "sharpe_original": s0, "sharpe_shifted": s1,
        "cagr_original": base.metrics["cagr"], "cagr_shifted": shifted.metrics["cagr"],
        "lag_bars": lag,
    }
    curves = {"original": base.equity, "shifted": shifted.equity}
    if s0 > 0.5 and drop > 0.5 and s1 < 0.5 * s0:
        verdict, msg = "FAIL", (f"Delaying the signal by {lag} bar dropped Sharpe from {s0:.2f} to {s1:.2f}: "
                                "the results depend on information that wasn't available yet.")
    elif drop > 0.3:
        verdict, msg = "WARN", f"Delaying the signal by {lag} bar dropped Sharpe from {s0:.2f} to {s1:.2f}; worth a closer look."
    else:
        verdict, msg = "PASS", f"Delaying the signal by {lag} bar barely changed results (Sharpe {s0:.2f} -> {s1:.2f})."
    return AttackResult("signal_shift", verdict, msg, metrics, curves)
