"""Offline tests for the LLM guardrails (no network calls, except the opt-in llm test)."""
import inspect
import json
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

import agent.planner as planner
from agent.interpreter import unverified_numbers
from agent.planner import plan_audit, plan_problems, verify_findings
from agent.sanitize import strip_hints
from attacks.evidence import report_to_evidence
from attacks.runner import run_audit
from engine.data import synthetic_prices
from strategies import STRATEGIES

GIVEAWAYS = ("BUG", "PLANTED_BUG", "Broken", "NAME =")


def test_strip_hints_removes_giveaways_and_keeps_line_numbers():
    for name, mod in STRATEGIES.items():
        src = inspect.getsource(mod)
        clean = strip_hints(src)
        assert len(clean.splitlines()) == len(src.splitlines()), name
        assert not any(g in clean for g in GIVEAWAYS), name
        for orig, new in zip(src.splitlines(), clean.splitlines()):
            assert new == "" or orig.startswith(new), name  # lines only get blanked or truncated


def test_strip_hints_keeps_real_code():
    clean = strip_hints(inspect.getsource(STRATEGIES["leaky"]))
    assert "center=True" in clean  # the actual bug must stay visible to the auditor


def test_verify_findings_checks_and_relocates_lines():
    src = "a = 1\nb = c.rolling(5, center=True).mean()\nreturn b"
    ok, bad = verify_findings([
        {"line": 2, "snippet": "c.rolling(5, center=True)"},     # correct
        {"line": 3, "snippet": "c.rolling(5, center=True)"},     # wrong line, unique snippet -> relocated
        {"line": 1, "snippet": "df.bfill()"},                    # not in the code -> rejected
    ], src)
    assert [f["line"] for f in ok] == [2, 2] and ok[1]["line_corrected_from"] == 3
    assert len(bad) == 1
    ok, bad = verify_findings([{"line": 2, "snippet": "b = c.rolling(5, center=True).mean()}, {"}], src)
    assert ok[0]["snippet_trimmed"] and ok[0]["snippet"] == "b = c.rolling(5, center=True).mean()" and not bad


def test_evidence_is_plain_json_with_no_ground_truth():
    ev = report_to_evidence(run_audit(STRATEGIES["overfit"], synthetic_prices(seed=7)))
    text = json.dumps(ev)  # must not raise on numpy types / tuples
    assert "PLANTED_BUG" not in text
    assert {t["test"] for t in ev["tests"]} == {"signal_shift", "point_in_time", "walk_forward", "deflated_sharpe"}


def test_unverified_numbers_flags_invented_values():
    ev = {"reported_metrics": {"sharpe": 3.4321, "cagr": 0.4987},
          "tests": [{"summary": "below 95%", "metrics": {"sharpe_shifted": -0.3612}}]}
    assert unverified_numbers("Sharpe 3.43 fell to ‑0.36; CAGR 50%, under 95%.", ev) == []
    assert unverified_numbers("Sharpe 2.10 and a 63% chance.", ev) == ["2.10", "63%"]


def _plan(tests=("signal_shift", "point_in_time", "walk_forward", "deflated_sharpe"), summary="Long above SMA.",
          review=()):
    return {"strategy_summary": summary, "searches_parameters": False, "findings": [],
            "test_plan": [{"test": t, "priority": "normal", "expected_verdict": "PASS", "hypothesis": "h"} for t in tests],
            "scan_review": [{"line": l, "rule": r, "verdict": "confirmed", "reason": "x"} for l, r in review]}


def test_plan_problems_flags_incomplete_plans():
    src = "a = 1\nb = 2\nc = x.shift(-1)\n"
    hit = [{"line": 3, "rule": "negative_shift"}]
    assert plan_problems(_plan(), src) == []
    assert plan_problems(_plan(review=[(3, "negative_shift")]), src, hit) == []
    assert plan_problems(_plan(tests=()), src)                              # empty test_plan (seen on Super)
    assert plan_problems(_plan(tests=("signal_shift", "signal_shift", "walk_forward", "deflated_sharpe")), src)
    assert plan_problems(_plan(summary=" "), src)
    assert plan_problems(_plan(), src, hit)                                 # hit not reviewed
    garbled = {**_plan(), "findings": [{"line": 3, "snippet": "c = x.shift(-1)}, {", "concern": "lookahead"}]}
    assert plan_problems(garbled, src)                                      # junk glued onto a snippet (seen on Super)


def test_plan_audit_retries_incomplete_plans(monkeypatch):
    replies = iter([_plan(tests=()), _plan(tests=()), _plan()])
    monkeypatch.setattr(planner, "chat_json", lambda *a, **k: next(replies))
    plan = planner.plan_audit("x = 1\n")
    assert plan["attempts"] == 3 and not plan["incomplete"]


def test_plan_audit_gives_up_but_keeps_going(monkeypatch):
    monkeypatch.setattr(planner, "chat_json", lambda *a, **k: _plan(tests=()))
    plan = planner.plan_audit("x = 1\n", max_attempts=2)
    assert plan["attempts"] == 2 and plan["incomplete"] and plan["problems"]


@pytest.mark.llm
@pytest.mark.skipif(os.getenv("RUN_LLM_TESTS") != "1", reason="set RUN_LLM_TESTS=1")
def test_planner_points_at_lookahead_block_every_time():
    mod = STRATEGIES["lookahead"]
    src = strip_hints(inspect.getsource(mod))
    with ThreadPoolExecutor(6) as pool:
        plans = list(pool.map(lambda _: plan_audit(src, mod.DESCRIPTION), range(6)))
    # L17 (the SMA today's close is compared to), L18 (the comparison) and L20 (unshifted return) are all
    # fair places to point; an incomplete plan (after retries) may have no findings, so allow at most one.
    lines = [{f["line"] for f in p["findings"]} for p in plans]
    assert sum(not (ls & {17, 18, 19, 20}) for ls in lines) <= 1, lines
