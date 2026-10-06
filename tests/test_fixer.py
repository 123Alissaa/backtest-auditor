"""Fix loop: pre-checks, acceptance and the retry loop (offline: LLM and sandbox are faked)."""
import json
from pathlib import Path

import pytest

import agent.fixer as fixer
from agent.fixer import accept, diff_lines, eligibility, precheck

SAMPLES = Path(__file__).resolve().parent.parent / "app" / "samples"
ORIGINAL = """import pandas as pd

DESCRIPTION = "Long above the 20-day average."


def run(prices, window=20):
    c = prices["close"]
    sma = c.rolling(window).mean()
    signal = (c > sma).astype(float)
    return signal
"""
GOOD = ORIGINAL.replace("return signal", "return signal.shift(1).fillna(0.0)")


def _ev(shift="PASS", pit="PASS", exposure=0.4, deflated="WARN"):
    return {"reported_metrics": {"sharpe": 0.1, "exposure": exposure},
            "tests": [{"test": "signal_shift", "verdict": shift, "summary": ""},
                      {"test": "point_in_time", "verdict": pit, "summary": ""},
                      {"test": "walk_forward", "verdict": "N/A", "summary": ""},
                      {"test": "deflated_sharpe", "verdict": deflated, "summary": ""}]}


def test_precheck_accepts_a_minimal_fix():
    assert precheck(GOOD, ORIGINAL) == []


@pytest.mark.parametrize("code, why", [
    ("def run(prices)\n", "syntax"),
    (ORIGINAL.replace("def run(", "def go("), "no run"),
    (ORIGINAL.replace("import pandas as pd", "import pandas as pd\nimport requests"), "imports"),
    (GOOD.replace("c.rolling(window)", "c.rolling(window, center=True)"), "center"),
    ("import pandas as pd\n\ndef run(prices):\n    return prices['close'] * 0 + 1\n", "too much"),
])
def test_precheck_rejects(code, why):
    assert precheck(code, ORIGINAL), why


def test_accept_rules():
    assert accept(_ev()) == []
    assert accept(_ev(shift="FAIL")) and accept(_ev(pit="WARN"))
    assert accept(_ev(deflated="FAIL"))
    assert accept(_ev(exposure=0.01))                       # a "fix" that never trades is no fix


def test_eligibility():
    assert eligibility(_ev(shift="FAIL"), {"searches_parameters": False})[0]
    assert not eligibility(_ev(shift="FAIL"), {"searches_parameters": True})[0]     # overfitting: explain, don't fake
    assert not eligibility(_ev(), {"searches_parameters": False})[0]                # nothing to fix


def test_diff_ignores_blank_line_noise():
    d = diff_lines("a\n\n\nreturn x\n", "a\nreturn x.shift(1)\n")
    changes = [ln for ln in d if ln[:1] in "+-" and not ln.startswith(("+++", "---"))]
    assert changes == ["-return x", "+return x.shift(1)"]


def test_loop_retries_with_feedback_then_accepts(monkeypatch):
    rounds = iter([
        [{"approach": "bad", "explanation": "", "code": ORIGINAL},     # unchanged: sandbox says still FAIL
         {"approach": "junk", "explanation": "", "code": "def run(prices)\n"}],  # syntax error: never run
        [{"approach": "shift", "explanation": "", "code": GOOD}],
    ])
    seen_history = []
    monkeypatch.setattr(fixer, "_ask_for_fixes", lambda src, ev, plan, hist: seen_history.append(len(hist)) or next(rounds))
    monkeypatch.setattr(fixer, "prepare_workspace", lambda prices: type("W", (), {"uuid": "ws"})())
    monkeypatch.setattr(fixer, "audit_variant", lambda ws, code: {
        "evidence": _ev() if ".shift(1)" in code else _ev(shift="FAIL", pit="FAIL"), "curves": {}})
    out = fixer.fix_strategy(ORIGINAL, _ev(shift="FAIL", pit="FAIL"), {"searches_parameters": False}, prices=None)
    assert seen_history == [0, 2]                            # round 2 saw both failed round-1 attempts
    assert [a["accepted"] for a in out["attempts"]] == [False, False, True] and out["accepted"] == 2
    assert out["attempts"][1]["evidence"] is None            # the syntax-error candidate never reached the sandbox


def test_saved_samples_are_fixable_or_explained():
    for name, fixable in (("lookahead", True), ("leaky", True), ("overfit", False), ("honest", False)):
        s = json.loads((SAMPLES / f"{name}.json").read_text())
        assert eligibility(s["evidence"], s["plan"])[0] is fixable, name


def test_diff_drops_context_only_hunks():
    before = "import pandas as pd\n\n\n\n\ndef run(p):\n    return s\n"
    after = "import pandas as pd\n\ndef run(p):\n    return s.shift(1)\n"
    hunks = [ln for ln in diff_lines(before, after) if ln.startswith("@@")]
    assert len(hunks) == 1
