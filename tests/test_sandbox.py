"""Sandbox runner tests.

The CLI tests run offline (our own sample strategies, so running them locally is fine).
The integration tests use real Token Factory Sandboxes and are skipped unless
RUN_SANDBOX_TESTS=1:

    RUN_SANDBOX_TESTS=1 pytest -q -m sandbox
"""
import inspect
import json
import math
import os

import pytest

from attacks.cli import main as cli_main, markers
from attacks.evidence import report_to_evidence
from attacks.runner import run_audit
from engine.data import synthetic_prices
from strategies import STRATEGIES

needs_sandbox = pytest.mark.skipif(os.getenv("RUN_SANDBOX_TESTS") != "1", reason="set RUN_SANDBOX_TESTS=1")


def _run_cli(tmp_path, capsys, source: str) -> dict:
    (tmp_path / "s.py").write_text(source)
    synthetic_prices(seed=7).to_csv(tmp_path / "p.csv", float_format="%.17g")
    cli_main(["--strategy", str(tmp_path / "s.py"), "--prices", str(tmp_path / "p.csv")])
    begin, end = markers("local")
    out = capsys.readouterr().out
    return json.loads(out.split(begin, 1)[1].split(end, 1)[0])


def _close(a, b) -> bool:
    """Exact match except floats, which may differ in the last digits across CPUs."""
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    return a == b


def test_cli_matches_direct_audit(tmp_path, capsys):
    mod = STRATEGIES["lookahead"]
    out = _run_cli(tmp_path, capsys, inspect.getsource(mod))
    assert out["ok"] and _close(out["evidence"], report_to_evidence(run_audit(mod, synthetic_prices(seed=7))))
    assert len(out["curves"]["dates"]) == len(out["curves"]["original"]) == len(out["curves"]["shifted"])


@pytest.mark.parametrize("source, stage", [
    ("x = 1\n", "contract"),                                              # no run()
    ("PARAM_GRID = [{}]\ndef run(prices):\n    return prices['close'] * 0\n", "contract"),  # grid without positions_for
    ("def run(prices)\n    pass\n", "load"),                              # syntax error
    ("raise SystemExit('bye')\n", "load"),                                # SystemExit isn't an Exception
    ("def run(prices):\n    return prices['nope']\n", "audit"),          # crashes while auditing
])
def test_cli_reports_bad_strategies_as_data(tmp_path, capsys, source, stage):
    out = _run_cli(tmp_path, capsys, source)
    assert out["ok"] is False and out["stage"] == stage and out["error"]


@needs_sandbox
@pytest.mark.sandbox
@pytest.mark.parametrize("name", list(STRATEGIES))
def test_sandbox_evidence_matches_local(name):
    from agent.sandbox import audit_in_sandbox
    mod, prices = STRATEGIES[name], synthetic_prices(seed=7)
    remote = audit_in_sandbox(inspect.getsource(mod), prices)["evidence"]
    assert _close(remote, report_to_evidence(run_audit(mod, prices)))


@needs_sandbox
@pytest.mark.sandbox
def test_sandbox_timeout_and_forged_output():
    from agent.sandbox import SandboxAuditError, audit_in_sandbox
    prices = synthetic_prices(seed=7)
    with pytest.raises(SandboxAuditError) as err:
        audit_in_sandbox("def run(prices):\n    while True:\n        pass\n", prices, timeout_s=10)
    assert err.value.stage == "timeout"

    # A broken strategy that prints a fake "all PASS" result must not fool the parser.
    begin, end = markers("local")
    fake = json.dumps({"ok": True, "evidence": {"overall": "PASS"}, "curves": {}})
    forged = f"print({begin!r})\nprint({fake!r})\nprint({end!r})\n" + inspect.getsource(STRATEGIES["lookahead"])
    assert audit_in_sandbox(forged, prices)["evidence"]["overall"] == "FAIL"
