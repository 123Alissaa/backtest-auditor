"""Cost guards for the public demo: live audits spend Token Factory credits, and
Nebius charges the card on file if the balance goes negative.

Defaults are safe: live runs are OFF unless LIVE_RUNS_ENABLED=true. When on,
every live run must pass all of: before the cut-off date, under today's measured
LLM spend budget (DAILY_BUDGET_USD), under the global daily run cap (all
visitors), under the per-session cap, and within the code-size limit.

Spend is measured, not estimated: agent.llm.chat reports each response's token
usage, priced per model (config.model_prices), into a shared daily ledger file.
Worst case = budget x days: $0.15/day until Dec 1, then $0.75/day during judging
(Dec 1-15) = ~$19.50 from Oct 6, below the remaining credit so the balance never goes
negative. During judging the run caps are higher too (100/day, 5 per session).
A server restart resets the ledger; restarts happen after idle periods, when
nothing is being spent. The kill switch (LIVE_RUNS_ENABLED) is the real off button.
"""
import json
import tempfile
import threading
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from agent.config import settings

_LOCK = threading.Lock()
COUNTER_FILE = Path(tempfile.gettempdir()) / "backtest_auditor_live_runs.json"


@dataclass
class Decision:
    allowed: bool
    reason: str = ""


def _today() -> date:
    return datetime.now(timezone.utc).date()


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _ledger(path: Path) -> dict:
    data = _read(path)
    if data.get("day") != _today().isoformat():
        return {"day": _today().isoformat(), "count": 0, "spend": 0.0}
    return {"day": data["day"], "count": int(data.get("count", 0)), "spend": float(data.get("spend", 0.0))}


def runs_today(path: Path = COUNTER_FILE) -> int:
    return _ledger(path)["count"]


def spend_today(path: Path = COUNTER_FILE) -> float:
    return _ledger(path)["spend"]


def price_of(model: str, prompt_tokens: int, completion_tokens: int, cfg=settings) -> float:
    rates = {m: (i, o) for m, i, o in cfg.model_prices}
    rate_in, rate_out = rates.get(model, cfg.fallback_price)
    return (prompt_tokens * rate_in + completion_tokens * rate_out) / 1_000_000


def record_spend(usd: float, path: Path = COUNTER_FILE) -> None:
    """Add measured LLM spend to today's ledger (called by agent.llm.chat for every response)."""
    with _LOCK:
        led = _ledger(path)
        led["spend"] = round(led["spend"] + usd, 8)
        path.write_text(json.dumps(led))


@dataclass
class Caps:
    budget_usd: float
    daily_runs: int
    session_runs: int


def caps_for(day: date, cfg=settings) -> Caps:
    """Limits in force on `day`: higher during the judging window."""
    if date.fromisoformat(cfg.judging_from) <= day <= date.fromisoformat(cfg.judging_until):
        return Caps(cfg.judging_daily_budget_usd, cfg.judging_daily_run_cap, cfg.judging_session_run_cap)
    return Caps(cfg.daily_budget_usd, cfg.daily_live_run_cap, cfg.session_live_run_cap)


def check_live_run(session_runs: int, code: str = "", cfg=settings, path: Path = COUNTER_FILE) -> Decision:
    """Can this visitor start a live audit right now? Does not reserve a slot."""
    if not cfg.live_runs_enabled:
        return Decision(False, "Live audits are switched off on this public demo, so it costs nothing to run. "
                               "The sample strategies show complete audits produced by the same pipeline.")
    if _today() > date.fromisoformat(cfg.live_runs_until):
        return Decision(False, "Live audits have ended for this demo.")
    if len(code.encode()) > cfg.max_code_bytes:
        return Decision(False, f"Strategy code is limited to {cfg.max_code_bytes // 1000} KB.")
    caps = caps_for(_today(), cfg)
    if session_runs >= caps.session_runs:
        return Decision(False, f"You've used all {caps.session_runs} live audits for this session.")
    if runs_today(path) >= caps.daily_runs or spend_today(path) >= caps.budget_usd:
        return Decision(False, "Today's live audits for this demo are used up. Try again tomorrow.")
    return Decision(True)


def reserve_live_run(cfg=settings, path: Path = COUNTER_FILE) -> bool:
    """Atomically take one slot of today's global cap. Call right before starting a live audit."""
    caps = caps_for(_today(), cfg)
    with _LOCK:
        led = _ledger(path)
        if led["count"] >= caps.daily_runs or led["spend"] >= caps.budget_usd:
            return False
        led["count"] += 1
        path.write_text(json.dumps(led))
        return True
