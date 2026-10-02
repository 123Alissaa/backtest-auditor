"""EXPLAIN step: Nemotron turns deterministic evidence into a plain-English report.

Guardrails (the LLM explains, it never decides):
- Verdicts are always overwritten with the deterministic ones from the tests.
- Every decimal/percentage the model writes is checked against the evidence
  metrics; anything that doesn't match is listed in `unverified_numbers`.
- Cited lines are checked against the source like the planner's findings.
"""
import json
import re

from agent.config import settings
from agent.llm import chat_json
from agent.planner import TESTS
from agent.sanitize import numbered

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string"},
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "test": {"type": "string", "enum": TESTS},
                    "verdict": {"type": "string", "enum": ["PASS", "WARN", "FAIL", "N/A"]},
                    "explanation": {"type": "string"},
                    "lines": {"type": "array", "items": {"type": "integer"}},
                },
                "required": ["test", "verdict", "explanation", "lines"],
                "additionalProperties": False,
            },
        },
        "fixes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"line": {"type": "integer"}, "fix": {"type": "string"}},
                "required": ["line", "fix"],
                "additionalProperties": False,
            },
        },
        "caveats": {"type": "string"},
    },
    "required": ["headline", "tests", "fixes", "caveats"],
    "additionalProperties": False,
}

SYSTEM = """You explain the results of a trading-backtest audit to a retail trader or finance student.

You receive: the numbered strategy code, an earlier audit plan (hypotheses, may be wrong), and EVIDENCE from deterministic tests. The evidence is the only source of truth.

How to read the tests:
- Timing convention: run() returns positions, and positions[t] is held from close[t-1] to close[t]. A position may only use data through close[t-1], so the FINAL signal must be shifted by one bar before it is returned. Shifting an intermediate feature (e.g. the moving average) while still comparing against today's close does NOT fix lookahead.
- signal_shift FAIL = results collapse when the signal is delayed a bar; usually lookahead. Exception: strategies with calendar rules (e.g. only trading some weekdays) can also fail it because the delay moves trades to the wrong weekdays. Then say that, rather than claiming lookahead.
- signal_shift PASS with point_in_time FAIL = a leaky FEATURE (e.g. a centered window): the future information survives one extra bar of delay. This pattern is expected for leakage, not a contradiction.
- point_in_time FAIL = position[t] changed when future data was hidden. Definite use of future information (lookahead, leaky features, or parameters chosen on the full history).
- walk_forward FAIL = the configuration picked on past data didn't hold up on unseen data (overfitting).
- deflated_sharpe: probability the edge is real after accounting for configurations tried. If another test FAILED for lookahead/leakage, a deflated_sharpe PASS means nothing: the inflated returns are fake. Say so. WARN with a single trial just means "not statistically proven", which is normal on random data and not a bug. Never suggest trying more configurations to fix it.
- If a strategy has no FAILs, the headline should say no evidence of lookahead, leakage or overfitting was found, and mention any WARN as "not proven", not "untrustworthy".

Rules:
- Copy each test's verdict exactly from the evidence. Never change a verdict.
- Use only numbers that appear in the evidence metrics (you may round to 2 decimals or whole percents). Never compute or invent new numbers.
- If the plan's hypothesis disagrees with the evidence, trust the evidence and say so briefly.
- Point to the exact code lines responsible (line numbers from the numbered code). Use [] if none.
- headline: one sentence a non-expert understands, e.g. whether the reported performance can be trusted.
- tests: one entry per test in the evidence, 1-3 sentences each, plain language, no jargon without a short explanation.
- fixes: concrete code changes for FAIL/WARN causes, tied to a line. Empty if nothing to fix.
- caveats: limits of this audit (synthetic data, a WARN means "not proven", not "broken").
- This is an educational tool, not financial advice.
Respond with JSON only, matching the schema."""

_NUM = re.compile(r"(?<![\w.])-?\d+\.\d+%?|(?<![\w.])-?\d+%")


def _metric_values(evidence: dict) -> list[float]:
    vals: list[float] = []

    def walk(x):
        if isinstance(x, bool):
            return
        if isinstance(x, (int, float)):
            vals.append(float(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(evidence.get("reported_metrics", {}))
    for t in evidence.get("tests", []):
        walk(t.get("metrics", {}))
        for tok in _NUM.findall(t.get("summary", "")):  # numbers the deterministic summary itself states, e.g. "95%"
            vals.append(float(tok.rstrip("%")) / 100 if tok.endswith("%") else float(tok))
    return vals


def unverified_numbers(text: str, evidence: dict) -> list[str]:
    """Decimals and percentages in `text` that don't match any evidence metric (after rounding)."""
    vals = _metric_values(evidence)
    text = re.sub("[‐‑‒–−]", "-", text)  # unicode hyphens / dashes / minus
    bad = []
    for tok in _NUM.findall(text):
        pct = tok.endswith("%")
        x = float(tok.rstrip("%"))
        decimals = len(tok.rstrip("%").split(".")[1]) if "." in tok else 0
        tol = 0.5 * 10 ** -decimals + 1e-9
        candidates = [v * 100 for v in vals] if pct else vals
        if not any(abs(c - x) <= tol for c in candidates):
            bad.append(tok)
    return bad


def interpret(clean_source: str, evidence: dict, plan: dict | None = None, model: str | None = None) -> dict:
    plan_view = None
    if plan:
        keys = ("strategy_summary", "searches_parameters", "findings", "test_plan", "scan_review")
        plan_view = {k: plan.get(k) for k in keys}
    user = (
        "Numbered strategy code:\n\n" + numbered(clean_source)
        + "\n\nAudit plan (hypotheses):\n" + json.dumps(plan_view, indent=2)
        + "\n\nEVIDENCE (source of truth):\n" + json.dumps(evidence, indent=2)
    )
    report = chat_json(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        model=model or settings.model_reasoning, schema=REPORT_SCHEMA, name="audit_report", max_tokens=8000,
    )

    truth = {t["test"]: t["verdict"] for t in evidence["tests"]}
    n_lines = len(clean_source.splitlines())
    overridden = []
    for t in report["tests"]:
        if t["test"] in truth and t["verdict"] != truth[t["test"]]:
            overridden.append({"test": t["test"], "llm_said": t["verdict"], "actual": truth[t["test"]]})
            t["verdict"] = truth[t["test"]]
        t["lines"] = [n for n in t["lines"] if 1 <= n <= n_lines]
    report["fixes"] = [f for f in report["fixes"] if 1 <= f["line"] <= n_lines]

    all_text = " ".join([report["headline"], report["caveats"]] + [t["explanation"] for t in report["tests"]]
                        + [f["fix"] for f in report["fixes"]])
    report["overall"] = evidence["overall"]
    report["verdicts_overridden"] = overridden
    report["unverified_numbers"] = unverified_numbers(all_text, evidence)
    report["model"] = model or settings.model_reasoning
    return report
