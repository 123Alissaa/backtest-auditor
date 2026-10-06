"""One full audit, shared by the UI and the CLI script.

    static scan (rules, free) -> tests (sandbox) -> {Nano explains hits | Super plans} -> Super explains

Tests run BEFORE any paid LLM call: user code often fails (no run(), syntax
errors, crashes), and failing first means a broken submission costs nothing.

User-submitted code is only ever parsed (ast) or sent to the sandbox -- never
imported or executed on the host.
"""
import ast
import inspect
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Callable

import pandas as pd

from agent.interpreter import interpret
from agent.planner import plan_audit
from agent.sandbox import SandboxAuditError, audit_in_sandbox
from agent.sanitize import strip_hints
from agent.scanner import explain_hits, static_scan

StepCallback = Callable[[str, str, float | None], None]   # (step, "running" | "done" | "error", seconds)


class AuditFailed(Exception):
    def __init__(self, message: str, stage: str, details: str = ""):
        super().__init__(message)
        self.stage, self.details = stage, details


def declared_description(source: str) -> str | None:
    """Read a top-level DESCRIPTION = "..." without executing anything."""
    try:
        for node in ast.parse(source).body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "DESCRIPTION" for t in node.targets):
                value = ast.literal_eval(node.value)
                return value if isinstance(value, str) else None
    except (SyntaxError, ValueError):
        pass
    return None


def _local_tests(module, prices: pd.DataFrame) -> dict:
    """For OUR sample strategies only (precomputing demo results, tests). Never for user code."""
    from attacks.evidence import report_curves, report_to_evidence
    from attacks.runner import run_audit
    report = run_audit(module, prices)
    return {"evidence": report_to_evidence(report), "curves": report_curves(report)}


def run_full_audit(source: str, prices: pd.DataFrame, *, on_step: StepCallback | None = None,
                   sample_module=None) -> dict:
    """Audit strategy `source`. Tests run in a Token Factory Sandbox unless `sample_module`
    (one of OUR strategies) is given, in which case they may run locally.

    Raises AuditFailed if the code can't be audited (before any paid LLM call)."""
    step = on_step or (lambda *_: None)
    timings: dict[str, float] = {}

    def timed(name, fn, *args, **kwargs):
        step(name, "running", None)
        t = time.time()
        try:
            out = fn(*args, **kwargs)
        except Exception:
            step(name, "error", time.time() - t)
            raise
        timings[name] = time.time() - t
        step(name, "done", timings[name])
        return out

    clean = strip_hints(source)
    try:
        hits = timed("scan", static_scan, clean)
    except SyntaxError as e:
        raise AuditFailed(f"The code has a syntax error on line {e.lineno}: {e.msg}", "load")

    try:
        if sample_module is not None:
            result = timed("tests", _local_tests, sample_module, prices)
        else:
            result = timed("tests", audit_in_sandbox, source, prices)
    except SandboxAuditError as e:
        raise AuditFailed(str(e), e.stage, e.details)

    description = declared_description(source)
    with ThreadPoolExecutor(max_workers=2) as pool:
        f_hits = pool.submit(timed, "explain_hits", explain_hits, hits)
        f_plan = pool.submit(timed, "plan", plan_audit, clean, description, scan_hits=[dict(h) for h in hits])
        hits, plan = f_hits.result(), f_plan.result()
    report = timed("report", interpret, clean, result["evidence"], plan)

    return {
        "source": clean,
        "static_hits": hits,
        "plan": plan,
        "evidence": result["evidence"],
        "curves": result["curves"],
        "report": report,
        "timings": timings,
        "sandbox": sample_module is None,
    }


def sample_source(module) -> str:
    return inspect.getsource(module)
