"""Offline tests for the LLM guardrails (no network calls)."""
import inspect
import json

from agent.evidence import report_to_evidence
from agent.interpreter import unverified_numbers
from agent.planner import verify_findings
from agent.sanitize import strip_hints
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
