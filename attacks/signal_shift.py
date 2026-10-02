"""Signal-shift test: delay every position and re-run.

An honest strategy barely changes -- a short delay doesn't matter much.
A strategy that peeks at the future collapses, because the peek is gone.

Calendar rules: a strategy that only trades some weekdays (e.g. Mondays) would
be broken by a one-day delay for a reason that has nothing to do with lookahead
-- every trade lands on a weekday it never meant to trade. For those we delay
each position to the same weekday one week later instead, which still removes
any peek at the future but keeps the weekdays aligned. Detection looks only at
the positions, so it works on any strategy. (Day-of-month or month rules are
not detected.)
"""
import pandas as pd

from attacks.base import AttackResult
from engine.backtest import run_backtest

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
ACTIVE_DAY, IDLE_DAY = 0.10, 0.02   # share of days with a position


def weekday_exposure(pos: pd.Series) -> dict[str, float]:
    """Share of days with a nonzero position, per weekday."""
    if not isinstance(pos.index, pd.DatetimeIndex):
        return {}
    share = (pos.fillna(0.0) != 0).groupby(pos.index.dayofweek).mean()
    return {WEEKDAYS[d]: float(v) for d, v in share.items()}


def is_calendar_dependent(exposure: dict[str, float]) -> bool:
    """Trades on some weekdays but (almost) never on others."""
    return len(exposure) > 1 and max(exposure.values()) > ACTIVE_DAY and min(exposure.values()) < IDLE_DAY


def delay_positions(pos: pd.Series, lag: int, same_weekday: bool) -> pd.Series:
    if same_weekday:  # next occurrence of the same weekday; robust to holidays, unlike shift(5)
        return pos.groupby(pos.index.dayofweek).shift(lag).fillna(0.0)
    return pos.shift(lag).fillna(0.0)


def signal_shift_test(run, prices: pd.DataFrame, lag: int = 1) -> AttackResult:
    pos = run(prices)
    exposure = weekday_exposure(pos)
    calendar = is_calendar_dependent(exposure)
    delay = f"{lag} week (same weekday)" if calendar else f"{lag} bar"
    base = run_backtest(prices, pos)
    shifted = run_backtest(prices, delay_positions(pos, lag, calendar))
    s0, s1 = base.metrics["sharpe"], shifted.metrics["sharpe"]
    drop = s0 - s1
    metrics = {
        "sharpe_original": s0, "sharpe_shifted": s1,
        "cagr_original": base.metrics["cagr"], "cagr_shifted": shifted.metrics["cagr"],
        "lag_bars": lag, "delay": delay, "calendar_dependent": calendar,
        "weekday_exposure": {d: round(v, 3) for d, v in exposure.items()},
    }
    if calendar:
        traded = [d for d, v in exposure.items() if v > ACTIVE_DAY]
        note = f" The strategy only trades on {', '.join(traded)}, so each trade was delayed to the same weekday a week later."
    else:
        note = ""
    curves = {"original": base.equity, "shifted": shifted.equity}
    if s0 > 0.5 and drop > 0.5 and s1 < 0.5 * s0:
        verdict, msg = "FAIL", (f"Delaying the signal by {delay} dropped Sharpe from {s0:.2f} to {s1:.2f}: "
                                "the results depend on information that wasn't available yet.")
    elif drop > 0.3:
        verdict, msg = "WARN", f"Delaying the signal by {delay} dropped Sharpe from {s0:.2f} to {s1:.2f}; worth a closer look."
    else:
        verdict, msg = "PASS", f"Delaying the signal by {delay} barely changed results (Sharpe {s0:.2f} -> {s1:.2f})."
    return AttackResult("signal_shift", verdict, msg + note, metrics, curves)
