"""Turn an AuditReport into plain JSON evidence.

This is the contract between the deterministic tests and everything else: the
sandbox will return exactly this shape, and the interpreter only ever sees this
(never equity curves, never PLANTED_BUG).
"""
import json
import math

import numpy as np

from attacks.runner import AuditReport


def _clean(value):
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def report_to_evidence(report: AuditReport) -> dict:
    return _clean({
        "overall": report.overall,
        "reported_metrics": report.reported_metrics,
        "tests": [{"test": r.name, "verdict": r.verdict, "summary": r.summary, "metrics": r.metrics}
                  for r in report.results],
    })


def report_curves(report: AuditReport) -> dict:
    """Reported vs delayed equity curves from the signal-shift test, for the chart."""
    shift = next(r for r in report.results if r.name == "signal_shift")
    return {
        "dates": [str(d.date()) for d in shift.curves["original"].index],
        "original": [round(float(x), 6) for x in shift.curves["original"]],  # chart only; keeps output small
        "shifted": [round(float(x), 6) for x in shift.curves["shifted"]],
        "delay": shift.metrics.get("delay", "1 bar"),
    }


def evidence_json(report: AuditReport) -> str:
    return json.dumps(report_to_evidence(report), indent=2)
