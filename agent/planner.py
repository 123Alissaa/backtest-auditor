"""PLAN step: Nemotron (reasoning model) reads strategy code and writes an audit plan.

The plan is a hypothesis, not evidence. It says which lines look suspicious and
what each deterministic test is expected to show; the tests themselves always
run and have the final say. Every line the model cites is checked against the
real source, so it can't point at code that isn't there.
"""
import json
import re

from agent.config import settings
from agent.llm import chat_json
from agent.sanitize import numbered

TESTS = ["signal_shift", "point_in_time", "walk_forward", "deflated_sharpe"]
CONCERNS = ["lookahead", "leakage", "overfitting", "other"]

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "strategy_summary": {"type": "string"},
        "searches_parameters": {"type": "boolean"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line": {"type": "integer"},
                    "snippet": {"type": "string"},
                    "concern": {"type": "string", "enum": CONCERNS},
                    "severity": {"type": "string", "enum": ["high", "medium", "low"]},
                    "explanation": {"type": "string"},
                },
                "required": ["line", "snippet", "concern", "severity", "explanation"],
                "additionalProperties": False,
            },
        },
        "test_plan": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "test": {"type": "string", "enum": TESTS},
                    "priority": {"type": "string", "enum": ["high", "normal", "low"]},
                    "expected_verdict": {"type": "string", "enum": ["PASS", "WARN", "FAIL", "N/A"]},
                    "hypothesis": {"type": "string"},
                },
                "required": ["test", "priority", "expected_verdict", "hypothesis"],
                "additionalProperties": False,
            },
        },
        "scan_review": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line": {"type": "integer"},
                    "rule": {"type": "string"},
                    "verdict": {"type": "string", "enum": ["confirmed", "dismissed"]},
                    "reason": {"type": "string"},
                },
                "required": ["line", "rule", "verdict", "reason"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["strategy_summary", "searches_parameters", "findings", "test_plan", "scan_review"],
    "additionalProperties": False,
}

SYSTEM = """You audit trading-strategy backtest code for three bugs that make backtests lie:
- lookahead: a position uses data from the same bar it trades (e.g. a signal not shifted before trading that bar's return)
- leakage: a feature uses future data even if the final signal is shifted (centered windows, full-sample normalization/fits, bfill, negative shifts)
- overfitting: parameters picked by searching many configurations on the full history

Timing convention of the engine: positions[t] is held from close[t-1] to close[t] and may only use data through close[t-1]. The engine does NOT shift positions for the strategy.

The code's entry point is run(prices) -> positions. prices is a DataFrame with a 'close' column and a daily DatetimeIndex.

Deterministic tests that will run regardless of your plan:
- signal_shift: delay positions one extra bar; a big Sharpe collapse means lookahead. Usually PASSES for leakage, because a leaky feature still carries future information after one extra bar.
- point_in_time: re-run on data truncated at t with close[t] nudged; position[t] must not change. Catches lookahead AND leakage AND full-sample parameter picking.
- walk_forward: needs a declared PARAM_GRID + positions_for; picks the best config on the first 60% and tests it on the rest. N/A if no parameter search is declared.
- deflated_sharpe: discounts the Sharpe for the number of configurations tried. On random-walk data, WARN is normal even for honest code.

Fields:
- strategy_summary: 1-2 plain-English sentences on what the strategy trades and when. Never empty.
- searches_parameters: true if the code tries multiple configurations (a grid, loop, or max/min over params) to pick what it trades.
- findings: suspicious lines (may be empty).
- scan_review: one entry per static-check hit you are given (empty list if none). The hits come from simple
  pattern rules: the code on that line really matches the pattern, but whether it is a real problem depends on
  context (e.g. a full-sample mean used only for reporting is fine). "confirmed" if it lets future data into
  positions, else "dismissed", with a one-sentence reason. Confirmed hits should also appear in findings.
- test_plan: one entry per test.

Rules:
- Cite only lines that exist in the numbered code. "snippet" must be copied exactly from that line.
- Only report findings you can justify from the code. An honest strategy should get an empty findings list.
- Include all four tests in test_plan, each with your expected verdict and a one-sentence hypothesis.
- Respond with JSON only, matching the schema."""


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s)


def verify_findings(findings: list[dict], source: str) -> tuple[list[dict], list[dict]]:
    """Keep findings whose snippet really is on the cited line (relocating it if the
    model got the number wrong). Returns (verified, rejected)."""
    lines = source.splitlines()
    verified, rejected = [], []
    for f in findings:
        snip = _norm(f.get("snippet", ""))
        line = f.get("line", 0)
        if snip and 1 <= line <= len(lines) and snip in _norm(lines[line - 1]):
            verified.append(f)
            continue
        hits = [i for i, text in enumerate(lines, start=1) if snip and snip in _norm(text)]
        if len(hits) == 1:
            verified.append({**f, "line": hits[0], "line_corrected_from": line})
            continue
        # Garbled JSON can glue junk onto a snippet (seen: "sma = c.rolling(window).mean()}, {").
        # If the snippet still contains the whole cited line, trust the line number.
        cited = _norm(lines[line - 1]) if 1 <= line <= len(lines) else ""
        if len(cited) >= 8 and cited in snip:
            verified.append({**f, "snippet": lines[line - 1].strip(), "snippet_trimmed": True})
        else:
            rejected.append(f)
    return verified, rejected


def plan_problems(plan: dict, clean_source: str, scan_hits: list[dict] | None = None) -> list[str]:
    """Why a schema-valid plan is still unusable. Seen on Super 2026-10-02: plans with an empty
    test_plan and no findings (~1 in 3 runs), and findings garbled inside the JSON (a second
    finding swallowed into the first one's snippet). Both were broken responses, not judgments."""
    problems = []
    verified, rejected = verify_findings(plan.get("findings", []), clean_source)
    if rejected or any(f.get("snippet_trimmed") for f in verified):
        problems.append("some findings don't match the code (garbled or invented)")
    tests = [t.get("test") for t in plan.get("test_plan", [])]
    if sorted(tests) != sorted(TESTS):
        problems.append(f"test_plan covers {sorted(tests)}, expected each of {TESTS} once")
    if not plan.get("strategy_summary", "").strip():
        problems.append("strategy_summary is empty")
    reviewed = {(r.get("line"), r.get("rule")) for r in plan.get("scan_review", [])}
    missing = [(h["line"], h["rule"]) for h in scan_hits or [] if (h["line"], h["rule"]) not in reviewed]
    if missing:
        problems.append(f"scan_review is missing {missing}")
    return problems


def plan_audit(clean_source: str, description: str | None = None, model: str | None = None,
               scan_hits: list[dict] | None = None, max_attempts: int = 3) -> dict:
    """clean_source must already be passed through agent.sanitize.strip_hints.
    scan_hits: output of agent.scanner.static_scan, for the planner to confirm or dismiss."""
    user = "Numbered strategy code:\n\n" + numbered(clean_source)
    if description:
        user = f"The author describes it as: {description}\n\n" + user
    hits_view = [{k: h[k] for k in ("line", "rule", "concern", "snippet")} for h in scan_hits or []]
    user += "\n\nStatic-check hits to review:\n" + (json.dumps(hits_view, indent=2) if hits_view else "(none)")
    for attempt in range(1, max_attempts + 1):
        plan = chat_json(
            [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            model=model or settings.model_reasoning, schema=PLAN_SCHEMA, name="audit_plan", max_tokens=8000,
        )
        problems = plan_problems(plan, clean_source, scan_hits)
        if not problems:
            break
    plan["attempts"], plan["incomplete"], plan["problems"] = attempt, bool(problems), problems
    plan["findings"], plan["rejected_findings"] = verify_findings(plan.get("findings", []), clean_source)
    plan["model"] = model or settings.model_reasoning
    return plan
