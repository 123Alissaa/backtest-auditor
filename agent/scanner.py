"""SCAN step: deterministic rules find known leak patterns; Nemotron Nano explains them.

    rules find -> Nano explains (cheap, bounded) -> Super judges (planner scan_review) -> sandbox tests prove

Why rules instead of an LLM scan: tested 2026-10-02, a Nano (and Super) checklist
scan found the right line only ~1 in 3 runs on the lookahead/overfit samples, and
Nano sometimes reasoned past 6000 tokens without answering. Syntactic patterns
are better found by parsing the code: instant, reproducible, can't invent lines.
Semantic bugs (a signal never shifted, picking the best grid config) stay with
the Super planner, which catches them reliably.

static_scan() only PARSES the code (ast), it never executes it, so it's safe on
the host even for user-submitted code.
"""
import ast

from agent.config import settings
from agent.llm import chat_json

RULES = {
    "centered_window": ("leakage", "high", "A centered rolling window averages bars on both sides, so each value includes future prices."),
    "negative_shift": ("lookahead", "high", "A negative shift pulls a future value back onto today's row."),
    "backfill": ("leakage", "high", "Backfilling fills gaps with values from later dates."),
    "full_sample_stat": ("leakage", "medium", "A statistic over the whole series uses future data if it feeds the signal "
                                             "(fine if it's only used for reporting)."),
    "full_sample_fit": ("leakage", "medium", "Fitting on all the data leaks future information unless the data was split first."),
    "future_index": ("lookahead", "medium", "Indexing at a later position (e.g. i + 1) reads a future value."),
}

WINDOW_METHODS = {"rolling", "expanding", "ewm", "groupby", "resample"}
STAT_METHODS = {"mean", "std", "var", "min", "max", "median", "quantile", "rank"}
STAT_MODULES = {"np", "numpy"}


def _const(node):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub) and isinstance(node.operand, ast.Constant) \
            and isinstance(node.operand.value, (int, float)):
        return -node.operand.value
    return None


def _kw(call: ast.Call, name: str):
    return next((_const(k.value) for k in call.keywords if k.arg == name), None)


def _after_window(node) -> bool:
    """True if the receiver chain contains .rolling()/.expanding()/... (so the stat is not full-sample)."""
    while isinstance(node, (ast.Call, ast.Attribute, ast.Subscript)):
        if isinstance(node, ast.Attribute) and node.attr in WINDOW_METHODS:
            return True
        node = node.func if isinstance(node, ast.Call) else node.value
    return False


def _rule_for_call(call: ast.Call) -> str | None:
    if not isinstance(call.func, ast.Attribute):
        return None
    attr, receiver = call.func.attr, call.func.value
    if attr == "rolling" and _kw(call, "center") is True:
        return "centered_window"
    if attr == "shift":
        n = _const(call.args[0]) if call.args else _kw(call, "periods")
        if isinstance(n, (int, float)) and n < 0:
            return "negative_shift"
    if attr in ("bfill", "backfill"):
        return "backfill"
    if attr == "fillna" and _kw(call, "method") in ("bfill", "backfill"):
        return "backfill"
    if attr == "interpolate" and _kw(call, "limit_direction") in ("backward", "both"):
        return "backfill"
    if attr in STAT_METHODS:
        if isinstance(receiver, ast.Name) and receiver.id in STAT_MODULES:
            return "full_sample_stat" if call.args else None
        if not _after_window(receiver):
            return "full_sample_stat"
    if attr in ("fit", "fit_transform"):
        return "full_sample_fit"
    return None


def _is_future_index(sub: ast.Subscript) -> bool:
    idx = sub.slice
    if isinstance(idx, ast.BinOp) and isinstance(idx.op, ast.Add):
        return any(isinstance(_const(side), (int, float)) and _const(side) > 0 for side in (idx.left, idx.right))
    return False


def static_scan(source: str) -> list[dict]:
    """Find rule hits in `source`. Returns [{line, snippet, rule, concern, confidence}], one per (line, rule)."""
    lines = source.splitlines()
    hits, seen = [], set()
    for node in ast.walk(ast.parse(source)):
        rule = None
        if isinstance(node, ast.Call):
            rule = _rule_for_call(node)
        elif isinstance(node, ast.Subscript) and _is_future_index(node):
            rule = "future_index"
        if rule and (node.lineno, rule) not in seen:
            seen.add((node.lineno, rule))
            concern, confidence, _ = RULES[rule]
            hits.append({"line": node.lineno, "snippet": lines[node.lineno - 1].strip(), "rule": rule,
                         "concern": concern, "confidence": confidence})
    return sorted(hits, key=lambda h: (h["line"], h["rule"]))


EXPLAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "explanations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "integer"}, "text": {"type": "string"}},
                "required": ["id", "text"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["explanations"],
    "additionalProperties": False,
}

EXPLAIN_SYSTEM = """You explain static-analysis hits in trading-strategy code to a retail trader or finance student.
Each hit comes with a FACT: a true statement about why this code pattern can leak future data into a backtest.
For each hit, write ONE plain-English sentence (max 30 words) that restates the fact for that specific line.
- Never say the line is safe, fine or has no leakage: deciding that is not your job (a reviewer does it later).
- If confidence is "medium", add that it depends on how the value is used.
- Don't invent numbers.
Respond with JSON only: {"explanations": [{"id": <hit id>, "text": "..."}]}."""


def explain_hits(hits: list[dict], model: str | None = None) -> list[dict]:
    """Add a one-sentence `explanation` to each hit using Nano. Never fails: falls back to the rule's description."""
    model = model or settings.model_fast
    for h in hits:
        h["explanation"], h["explained_by"] = RULES[h["rule"]][2], "rule"
    if not hits:
        return hits
    listing = "\n".join(f"id={i} line={h['line']} confidence={h['confidence']} code: {h['snippet']}\n"
                        f"     FACT: {RULES[h['rule']][2]}" for i, h in enumerate(hits))
    try:
        out = chat_json([{"role": "system", "content": EXPLAIN_SYSTEM}, {"role": "user", "content": listing}],
                        model=model, schema=EXPLAIN_SCHEMA, name="hit_explanations", retries=0,
                        max_tokens=1500, timeout=30)
    except Exception:  # over-thinking, timeout, bad JSON: the rule text is a fine fallback
        return hits
    for e in out.get("explanations", []):
        if 0 <= e.get("id", -1) < len(hits) and e.get("text", "").strip():
            hits[e["id"]]["explanation"], hits[e["id"]]["explained_by"] = e["text"].strip(), model
    return hits
