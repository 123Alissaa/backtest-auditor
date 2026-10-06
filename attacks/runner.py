"""Runs every attack against one strategy. The auditor never reads PLANTED_BUG."""
from dataclasses import dataclass

import pandas as pd

from attacks.base import AttackResult
from attacks.overfitting import deflated_sharpe_test, walk_forward_test
from attacks.point_in_time import point_in_time_test
from attacks.signal_shift import signal_shift_test
from engine.backtest import run_backtest


@dataclass
class AuditReport:
    strategy: str
    reported_metrics: dict
    results: list[AttackResult]

    @property
    def overall(self) -> str:
        verdicts = {r.verdict for r in self.results}
        return "FAIL" if "FAIL" in verdicts else "WARN" if "WARN" in verdicts else "PASS"


def run_audit(strategy, prices: pd.DataFrame) -> AuditReport:
    reported = run_backtest(prices, strategy.run(prices)).metrics
    results = [
        signal_shift_test(strategy.run, prices),
        # 40 dates catch small leaks (e.g. a full-history z-score flips positions only on some days); strategies
        # with a parameter grid re-run their whole search per check, so they get 12. Depends only on the code.
        point_in_time_test(strategy.run, prices, n_checks=12 if getattr(strategy, "PARAM_GRID", None) else 40),
        walk_forward_test(strategy, prices),
        deflated_sharpe_test(strategy, prices),
    ]
    return AuditReport(strategy.NAME, reported, results)
