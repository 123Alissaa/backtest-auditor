"""FIX step: Nemotron Super rewrites the strategy; the sandbox proves (or disproves) each fix.

    snapshot workspace once -> Super writes 2 candidate fixes -> free pre-checks
      -> each candidate runs all attacks in its own sandbox branch (parallel)
      -> accept the first that passes; otherwise feed the failures back for one more round

The AI writes code, the tests decide. A fix is accepted only if the hide-the-future
test PASSes (the definitive no-future-data check), nothing FAILs, and the strategy
still trades. The delay test may WARN: on random data a short-term honest signal's
Sharpe can move >0.3 when delayed by chance (seen: the correct minimal fix for the
next_day sample was rejected for a delay-test WARN when PASS was required).
Pre-checks stop "fixes" that change the strategy into something else.

Scope: lookahead and leakage are code bugs and can be fixed in code. Overfitting
(choosing settings with hindsight) is a research-process problem; editing code
can't undo it without new data, so we say so instead of faking a fix.
"""
import ast
import difflib
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from agent.config import settings
from agent.llm import chat_json
from agent.sandbox import SandboxAuditError, audit_variant, prepare_workspace
from agent.sanitize import numbered
from agent.scanner import static_scan

MAX_ROUNDS = 2
CANDIDATES = 2
MIN_SIMILARITY = 0.55     # fixed code must stay recognisably the same strategy
MIN_EXPOSURE = 0.05       # must still hold a position on >= 5% of days
ALLOWED_IMPORTS = {"numpy", "pandas", "math", "itertools", "functools", "statistics"}

FIX_SCHEMA = {
    "type": "object",
    "properties": {
        "fixes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "approach": {"type": "string"},
                    "explanation": {"type": "string"},
                    "code": {"type": "string"},
                },
                "required": ["approach", "explanation", "code"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["fixes"],
    "additionalProperties": False,
}

SYSTEM = f"""You fix trading-strategy code that uses future information (lookahead or data leakage).

Engine timing convention: run(prices) returns positions; positions[t] is held from close[t-1] to close[t] and may
only use data through close[t-1]. The engine does NOT shift positions. So the FINAL signal must be shifted forward
one bar (.shift(1)), and every feature must only use past data (no center=True, no negative shifts, no bfill,
no statistics or fits over the whole series; use rolling/expanding windows instead).

Write exactly {CANDIDATES} DIFFERENT minimal fixes. Rules:
- Keep the same strategy idea, function names, signature, parameters and DESCRIPTION. Change as little as possible.
- Return the complete corrected file in "code" (plain Python, no markdown fences).
- Only import numpy, pandas or the standard library.
- Don't try to improve returns. An honest strategy on random data should earn about nothing.
- "approach": a short label (max 8 words). "explanation": one plain-English sentence on what changed and why.
Respond with JSON only."""


# ---------- deterministic checks (free) ----------

def _imports(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def similarity(a: str, b: str) -> float:
    strip = lambda s: [ln.strip() for ln in s.splitlines() if ln.strip()]  # noqa: E731
    return difflib.SequenceMatcher(None, strip(a), strip(b)).ratio()


def precheck(code: str, original: str) -> list[str]:
    """Why a candidate fix shouldn't even be run. Empty list = OK to test."""
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"syntax error on line {e.lineno}: {e.msg}"]
    problems = []
    if not any(isinstance(n, ast.FunctionDef) and n.name == "run" for n in tree.body):
        problems.append("no run(prices) function")
    extra = _imports(tree) - _imports(ast.parse(original)) - ALLOWED_IMPORTS
    if extra:
        problems.append(f"new imports not allowed: {sorted(extra)}")
    hits = [h for h in static_scan(code) if h["confidence"] == "high"]
    if hits:
        problems.append("still contains " + ", ".join(f"{h['rule']} (line {h['line']})" for h in hits))
    sim = similarity(code, original)
    if sim < MIN_SIMILARITY:
        problems.append(f"changes too much of the strategy (similarity {sim:.0%})")
    return problems


def accept(evidence: dict) -> list[str]:
    """Why sandbox evidence doesn't count as fixed. Empty list = fixed."""
    v = {t["test"]: t["verdict"] for t in evidence["tests"]}
    reasons = [] if v.get("point_in_time") == "PASS" else [f"point_in_time is {v.get('point_in_time')}"]
    reasons += [f"{t} FAILs" for t, verdict in v.items() if verdict == "FAIL" and t != "point_in_time"]
    exposure = evidence["reported_metrics"].get("exposure")
    if exposure is not None and exposure < MIN_EXPOSURE:
        reasons.append(f"barely trades any more (in the market {exposure:.0%} of days)")
    return reasons


def eligibility(evidence: dict, plan: dict) -> tuple[bool, str]:
    v = {t["test"]: t["verdict"] for t in evidence["tests"]}
    if plan.get("searches_parameters"):
        return False, ("This strategy picks its settings by searching the full history (overfitting). That's a "
                       "research-process problem, not a code bug: no code edit can un-see the data. The honest fix is "
                       "to choose settings on older data only and judge them on data they've never seen.")
    if "FAIL" not in (v.get("signal_shift"), v.get("point_in_time")):
        return False, "No lookahead or leakage was found, so there's nothing to fix in the code."
    return True, ""


def diff_lines(before: str, after: str) -> list[str]:
    """Unified diff without blank-line noise (hint-stripped code is full of blank lines)."""
    lines = difflib.unified_diff(before.splitlines(), after.splitlines(), "original", "fixed", lineterm="", n=1)
    lines = [ln for ln in lines if not (ln[:1] in "+-" and not ln.startswith(("+++", "---")) and not ln[1:].strip())]
    out, hunk = [], []
    for ln in lines + ["@@"]:                     # sentinel flushes the last hunk
        if ln.startswith("@@"):
            if any(x[:1] in "+-" for x in hunk[1:]):  # keep only hunks that still change something
                out += hunk
            hunk = [ln]
        elif ln.startswith(("+++", "---")):
            out.append(ln)
        else:
            hunk.append(ln)
    return out


# ---------- the loop ----------

def _ask_for_fixes(source: str, evidence: dict, plan: dict, history: list[dict]) -> list[dict]:
    failing = [f"- {t['test']}: {t['verdict']}. {t['summary']}" for t in evidence["tests"] if t["verdict"] == "FAIL"]
    flagged = [f"- line {f['line']} ({f['concern']}): {f['explanation']}" for f in plan.get("findings", [])]
    user = ("Numbered strategy code:\n\n" + numbered(source)
            + "\n\nFailing tests:\n" + "\n".join(failing)
            + ("\n\nSuspicious lines:\n" + "\n".join(flagged) if flagged else ""))
    if history:
        user += "\n\nPrevious fixes that did NOT work (try something different):\n" + "\n".join(
            f"- {a['approach']}: {'; '.join(a['problems'])}" for a in history)
    out = chat_json([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
                    model=settings.model_reasoning, schema=FIX_SCHEMA, name="strategy_fixes", max_tokens=8000)
    return [f for f in out.get("fixes", []) if f.get("code", "").strip()][:CANDIDATES]


def fix_strategy(source: str, evidence: dict, plan: dict, prices: pd.DataFrame, on_step=None) -> dict:
    """Try to fix lookahead/leakage in `source` (hint-stripped code). Never raises for a failed fix."""
    step = on_step or (lambda *_: None)
    ok, reason = eligibility(evidence, plan)
    if not ok:
        return {"eligible": False, "reason": reason, "attempts": [], "accepted": None}

    t0 = time.time()
    step("workspace", "running", None)
    workspace = prepare_workspace(prices)
    step("workspace", "done", time.time() - t0)

    attempts: list[dict] = []
    for rnd in range(1, MAX_ROUNDS + 1):
        name = f"round{rnd}"
        step(name, "running", None)
        t = time.time()
        candidates = _ask_for_fixes(source, evidence, plan, [a for a in attempts if not a["accepted"]])
        batch = [{"round": rnd, "approach": c["approach"], "explanation": c["explanation"], "code": c["code"].strip() + "\n",
                  "problems": precheck(c["code"], source), "evidence": None, "curves": None, "accepted": False}
                 for c in candidates]
        runnable = [a for a in batch if not a["problems"]]

        def test(a):
            try:
                out = audit_variant(workspace, a["code"])
                a["evidence"], a["curves"] = out["evidence"], out["curves"]
                a["problems"] = accept(out["evidence"])
            except SandboxAuditError as e:
                a["problems"] = [f"crashed in the sandbox ({e.stage}): {e}"]
            return a

        with ThreadPoolExecutor(max_workers=CANDIDATES) as pool:  # one sandbox branch per candidate
            list(pool.map(test, runnable))
        for a in batch:
            a["accepted"] = not a["problems"]
        attempts += batch
        step(name, "done", time.time() - t)
        if any(a["accepted"] for a in batch):
            break

    accepted = next((i for i, a in enumerate(attempts) if a["accepted"]), None)
    result = {"eligible": True, "reason": "", "attempts": attempts, "accepted": accepted,
              "workspace": str(workspace.uuid), "seconds": round(time.time() - t0, 1)}
    if accepted is not None:
        result["diff"] = diff_lines(source, attempts[accepted]["code"])
    return result
