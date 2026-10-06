"""Cost guards for the public demo: live audits spend Token Factory credits, and
Nebius charges the card on file if the balance goes negative.

Defaults are safe: live runs are OFF unless LIVE_RUNS_ENABLED=true. When on,
every live run must pass all of: before the cut-off date, under the global daily
cap (all visitors), under the per-session cap, and within the code-size limit.

The daily counter lives in a file so all sessions share it. A server restart can
reset it, so the cap bounds spend per process-day rather than guaranteeing zero;
the kill switch (LIVE_RUNS_ENABLED) is the real off button.
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


def runs_today(path: Path = COUNTER_FILE) -> int:
    data = _read(path)
    return int(data.get("count", 0)) if data.get("day") == _today().isoformat() else 0


def check_live_run(session_runs: int, code: str = "", cfg=settings, path: Path = COUNTER_FILE) -> Decision:
    """Can this visitor start a live audit right now? Does not reserve a slot."""
    if not cfg.live_runs_enabled:
        return Decision(False, "Live audits are switched off on this public demo, so it costs nothing to run. "
                               "The sample strategies show complete audits produced by the same pipeline.")
    if _today() > date.fromisoformat(cfg.live_runs_until):
        return Decision(False, "Live audits have ended for this demo.")
    if len(code.encode()) > cfg.max_code_bytes:
        return Decision(False, f"Strategy code is limited to {cfg.max_code_bytes // 1000} KB.")
    if session_runs >= cfg.session_live_run_cap:
        return Decision(False, f"You've used all {cfg.session_live_run_cap} live audits for this session.")
    if runs_today(path) >= cfg.daily_live_run_cap:
        return Decision(False, "Today's live audits for this demo are used up. Try again tomorrow.")
    return Decision(True)


def reserve_live_run(cfg=settings, path: Path = COUNTER_FILE) -> bool:
    """Atomically take one slot of today's global cap. Call right before starting a live audit."""
    with _LOCK:
        count = runs_today(path)
        if count >= cfg.daily_live_run_cap:
            return False
        path.write_text(json.dumps({"day": _today().isoformat(), "count": count + 1}))
        return True
