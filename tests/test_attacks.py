"""Each broken strategy must be caught by the right test; the honest one must never FAIL.
Runs on several random seeds so we're not tuned to one lucky dataset."""
import pytest

from attacks.runner import run_audit
from engine.data import synthetic_prices
from strategies import STRATEGIES

SEEDS = [7, 23]


def verdicts(report):
    return {r.name: r.verdict for r in report.results}


@pytest.mark.parametrize("seed", SEEDS)
def test_honest_never_fails(seed):
    v = verdicts(run_audit(STRATEGIES["honest"], synthetic_prices(seed=seed)))
    assert "FAIL" not in v.values(), v


@pytest.mark.parametrize("seed", SEEDS)
def test_lookahead_is_caught(seed):
    v = verdicts(run_audit(STRATEGIES["lookahead"], synthetic_prices(seed=seed)))
    assert v["signal_shift"] == "FAIL" and v["point_in_time"] == "FAIL", v


@pytest.mark.parametrize("seed", SEEDS)
def test_leakage_is_caught_even_though_shift_passes(seed):
    v = verdicts(run_audit(STRATEGIES["leaky"], synthetic_prices(seed=seed)))
    assert v["point_in_time"] == "FAIL", v


@pytest.mark.slow
@pytest.mark.parametrize("seed", SEEDS)
def test_overfitting_is_caught(seed):
    v = verdicts(run_audit(STRATEGIES["overfit"], synthetic_prices(seed=seed)))
    assert v["deflated_sharpe"] == "FAIL", v
    assert v["walk_forward"] in ("FAIL", "WARN"), v


def _lookahead_on_mon_thu(prices):
    """Lookahead bug plus a weekday filter: must still be caught."""
    return STRATEGIES["lookahead"].run(prices) * prices.index.dayofweek.isin((0, 3))


@pytest.mark.parametrize("seed", SEEDS)
def test_signal_shift_keeps_weekdays_for_calendar_strategies(seed):
    from attacks.signal_shift import signal_shift_test
    prices = synthetic_prices(seed=seed)
    overfit = signal_shift_test(STRATEGIES["overfit"].run, prices)
    assert overfit.metrics["calendar_dependent"] and overfit.verdict != "FAIL", overfit.summary
    sneaky = signal_shift_test(_lookahead_on_mon_thu, prices)
    assert sneaky.metrics["calendar_dependent"] and sneaky.verdict == "FAIL", sneaky.summary


@pytest.mark.parametrize("name", ["honest", "lookahead", "leaky"])
def test_signal_shift_unchanged_for_everyday_strategies(name):
    from attacks.signal_shift import signal_shift_test
    r = signal_shift_test(STRATEGIES[name].run, synthetic_prices(seed=7))
    assert not r.metrics["calendar_dependent"] and r.metrics["delay"] == "1 bar"
