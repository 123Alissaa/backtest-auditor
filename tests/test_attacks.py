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
