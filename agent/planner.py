"""PLAN step: Nemotron (reasoning model) reads strategy code and writes an audit plan.

The plan is a hypothesis, not evidence. It says which lines look suspicious and
what each deterministic test is expected to show; the tests themselves always
run and have the final say. Every line the model cites is checked against the
real source, so it can't point at code that isn't there.
"""
import json
import re

from agent.config import settings
from agent.llm import chat
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
    },
    "required": ["strategy_summary", "searches_parameters", "findings", "test_plan"],
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
        else:
            rejected.append(f)
    return verified, rejected


def plan_audit(clean_source: str, description: str | None = None, model: str | None = None) -> dict:
    """clean_source must already be passed through agent.sanitize.strip_hints."""
    user = "Numbered strategy code:\n\n" + numbered(clean_source)
    if description:
        user = f"The author describes it as: {description}\n\n" + user
    reply = chat(
        [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
        model=model or settings.model_reasoning,
        response_format={"type": "json_schema", "json_schema": {"name": "audit_plan", "schema": PLAN_SCHEMA, "strict": True}},
        max_tokens=8000,
    )
    plan = json.loads(reply.content)
    plan["findings"], plan["rejected_findings"] = verify_findings(plan.get("findings", []), clean_source)
    plan["model"] = model or settings.model_reasoning
    return plan
