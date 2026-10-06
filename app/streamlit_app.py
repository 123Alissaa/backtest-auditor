"""Backtest Auditor web UI (Streamlit).

    streamlit run app/streamlit_app.py

Sample strategies load saved audits (app/samples/*.json, made by
scripts/precompute_samples.py), so viewing the demo makes no paid calls.
Live audits are OFF unless LIVE_RUNS_ENABLED=true and are capped (agent/limits.py).
User code is never executed here: it is only parsed, or sent to a Token Factory Sandbox.
"""
import html
import io
import json
import os
import queue
import sys
import threading
import time
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Backtest Auditor", page_icon="🔍", layout="wide")

# Streamlit Cloud keeps secrets in st.secrets; agent.config reads env vars. Bridge before importing it.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, (str, int, float, bool)):
            os.environ.setdefault(_k, str(_v))
except Exception:  # no secrets file locally -> .env is used instead
    pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import altair as alt  # noqa: E402
import pandas as pd  # noqa: E402

from agent.config import settings  # noqa: E402
from agent.interpreter import drop_noop_fixes  # noqa: E402
from agent.limits import check_live_run, reserve_live_run  # noqa: E402
from agent.fixer import diff_lines, eligibility, fix_strategy  # noqa: E402
from agent.pipeline import AuditFailed, run_full_audit  # noqa: E402
from engine.data import synthetic_prices  # noqa: E402

SAMPLES_DIR = Path(os.getenv("BA_SAMPLES_DIR", ROOT / "app" / "samples"))
SAMPLES = {  # display order: the most dramatic first
    "lookahead": "Lookahead: 50% a year?",
    "leaky": "Leaky: smoothed trend",
    "overfit": "Overfit: best of 279",
    "honest": "Honest: 50/200 crossover",
}
CUSTOM = "Your own strategy"

STEPS = [
    ("scan", "Static scan", "rules, no AI"),
    ("tests", "Attack tests", "Token Factory Sandbox"),
    ("explain_hits", "Explain rule hits", "Nemotron Nano"),
    ("plan", "Plan the audit", "Nemotron Super"),
    ("report", "Write the report", "Nemotron Super"),
]
FIX_STEPS = [
    ("workspace", "Sandbox snapshot", "Token Factory Sandbox, made once"),
    ("round1", "Write 2 fixes and test each in its own branch", "Nemotron Super + parallel sandbox branches"),
    ("round2", "Second attempt with the failures as feedback", "only if needed"),
]
TESTS = {
    "signal_shift": ("Delay test", "Delays every trade. Honest results barely change; peeking ones collapse."),
    "point_in_time": ("Hide-the-future test", "Re-runs with the future hidden. Positions must not change."),
    "walk_forward": ("Unseen-data test", "Picks settings on old data, then tests them on data it never saw."),
    "deflated_sharpe": ("Luck test", "Discounts the result for how many settings were tried."),
}
STATUS = {  # reserved status colors; always shown with an icon + label, never color alone
    "PASS": ("#0ca30c", "✓", "Pass"),
    "WARN": ("#fab219", "!", "Warning"),
    "FAIL": ("#d03b3b", "✕", "Fail"),
    "N/A": ("#8a8984", "–", "Not applicable"),
}
SERIES = {  # categorical slots 1-2, validated light + dark (dataviz validate_palette.js)
    "light": ("#2a78d6", "#eb6834"),
    "dark": ("#3987e5", "#d95926"),
}

TEMPLATE = '''import pandas as pd

DESCRIPTION = "Long when the 10-day average is above the 50-day average."


def run(prices: pd.DataFrame) -> pd.Series:
    """prices has a 'close' column and a daily DatetimeIndex. Return positions (0..1)."""
    c = prices["close"]
    signal = (c.rolling(10).mean() > c.rolling(50).mean()).astype(float)
    return signal.shift(1).fillna(0.0)  # decide at yesterday's close, hold today
'''

CSS = """
<style>
.ba-banner {border-left: 6px solid var(--ba-c); background: color-mix(in srgb, var(--ba-c) 12%, transparent);
  padding: 14px 18px; border-radius: 8px; margin: 4px 0 12px;}
.ba-banner .ba-label {font-weight: 700; font-size: 0.95rem; letter-spacing: .02em;}
.ba-banner .ba-head {font-size: 1.25rem; font-weight: 600; margin-top: 4px; line-height: 1.35;}
.ba-icon {display: inline-flex; align-items: center; justify-content: center; width: 1.4em; height: 1.4em;
  border-radius: 50%; background: var(--ba-c); color: #fff; font-weight: 700; margin-right: 6px; font-size: .85em;}
.ba-card {border: 1px solid color-mix(in srgb, currentColor 15%, transparent); border-top: 4px solid var(--ba-c);
  border-radius: 8px; padding: 12px 14px; height: 100%;}
.ba-card h4 {margin: 6px 0 2px; font-size: 1rem;}
.ba-card .ba-what {opacity: .7; font-size: .8rem; margin-bottom: 8px;}
.ba-card .ba-why {font-size: .9rem; line-height: 1.4;}
.ba-card .ba-raw {opacity: .7; font-size: .78rem; margin-top: 8px;
  border-top: 1px solid color-mix(in srgb, currentColor 12%, transparent); padding-top: 6px;}
.ba-code {font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .82rem; line-height: 1.5;
  border: 1px solid color-mix(in srgb, currentColor 15%, transparent); border-radius: 8px; overflow-x: auto;}
.ba-code table {border-collapse: collapse; width: 100%;}
.ba-code td {padding: 0 10px; white-space: pre; vertical-align: top;}
.ba-code td.ln {text-align: right; opacity: .45; user-select: none; width: 1%;}
.ba-code tr.hit {background: color-mix(in srgb, #d03b3b 16%, transparent);}
.ba-code tr.hit td.ln {opacity: 1; font-weight: 700; color: #d03b3b;}
.ba-step {display: flex; gap: 10px; align-items: baseline; font-size: .9rem; padding: 2px 0;}
.ba-step .t {opacity: .6; margin-left: auto; font-variant-numeric: tabular-nums;}
.ba-step .who {opacity: .6; font-size: .8rem;}
.ba-diff {font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .82rem; line-height: 1.5;
  border: 1px solid color-mix(in srgb, currentColor 15%, transparent); border-radius: 8px; padding: 6px 0; overflow-x: auto;}
.ba-diff div {white-space: pre; padding: 0 12px;}
.ba-diff .add {background: color-mix(in srgb, #0ca30c 16%, transparent);}
.ba-diff .del {background: color-mix(in srgb, #d03b3b 16%, transparent);}
.ba-diff .hunk {opacity: .5;}
.ba-attempt {display: flex; gap: 10px; align-items: baseline; padding: 4px 0; font-size: .9rem;}
.ba-attempt .why {opacity: .7; font-size: .82rem;}
[data-testid="stMainBlockContainer"] {padding-top: 3.8rem;}
.ba-hero {border: 1px solid color-mix(in srgb, currentColor 14%, transparent); border-radius: 12px;
  padding: 18px 22px 14px; margin-bottom: 6px;}
.ba-hero h1 {font-size: 1.9rem; margin: 0 0 4px; padding: 0; line-height: 1.2;}
.ba-hero .pitch {font-size: 1rem; opacity: .85; margin-bottom: 14px; max-width: 62rem; line-height: 1.45;}
.ba-steps {display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px;}
.ba-steps .s {border-radius: 8px; padding: 8px 10px; background: color-mix(in srgb, currentColor 5%, transparent);}
.ba-steps .n {display: inline-flex; width: 1.5em; height: 1.5em; border-radius: 50%; align-items: center;
  justify-content: center; background: #3987e5; color: #fff; font-weight: 700; font-size: .8rem; margin-right: 6px;}
.ba-steps .t {font-weight: 700; font-size: .92rem;}
.ba-steps .d {font-size: .8rem; opacity: .75; margin-top: 3px; line-height: 1.35;}
.ba-built {font-size: .78rem; opacity: .65; margin-top: 10px;}
@media (max-width: 760px) {
  .ba-steps {grid-template-columns: 1fr 1fr;}
  .ba-hero h1 {font-size: 1.5rem;}
}
.stTextArea textarea {font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .85rem;}
</style>
"""


# ---------- data ----------

@st.cache_data
def load_sample(name: str) -> dict | None:
    path = SAMPLES_DIR / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


@st.cache_data
def default_prices(seed: int) -> pd.DataFrame:
    return synthetic_prices(seed=seed)


def parse_prices(upload) -> tuple[pd.DataFrame | None, str]:
    """Uploaded CSV -> prices. Data only: pandas parses it, nothing is executed."""
    try:
        df = pd.read_csv(upload, index_col=0, parse_dates=True)
    except Exception as e:
        return None, f"Couldn't read the CSV: {e}"
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "close" not in df.columns:
        return None, "The CSV needs a 'close' column (first column = dates)."
    if not isinstance(df.index, pd.DatetimeIndex):
        return None, "The first column must be dates."
    df = df[["close"]].apply(pd.to_numeric, errors="coerce").dropna().sort_index()
    if len(df) < 400:
        return None, "Need at least 400 daily prices (the tests use 300 days of history)."
    if len(df) > settings.max_price_rows:
        return None, f"At most {settings.max_price_rows:,} rows."
    return df, ""


# ---------- small renderers ----------

def status_html(verdict: str) -> tuple[str, str, str]:
    color, icon, label = STATUS.get(verdict, STATUS["N/A"])
    return color, f'<span class="ba-icon" style="--ba-c:{color}">{icon}</span>', label


def render_steps(timings: dict, saved_at: str | None = None):
    rows = []
    for key, name, who in STEPS:
        t = timings.get(key)
        rows.append(f'<div class="ba-step">✓ <b>{name}</b> <span class="who">{who}</span>'
                    f'<span class="t">{"" if t is None else f"{t:.1f}s"}</span></div>')
    st.markdown("".join(rows), unsafe_allow_html=True)
    if saved_at:
        st.caption(f"Saved audit from {saved_at}: same pipeline as a live run, shown instantly.")


def run_with_progress(label: str, steps: list, work) -> dict | None:
    """Run work(on_step) in a worker thread; stream step updates from the main thread."""
    events: queue.Queue = queue.Queue()
    out: dict = {}

    def target():
        try:
            out["result"] = work(lambda n, s, t: events.put((n, s, t)))
        except Exception as e:  # surfaced below
            out["error"] = e

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    state = {k: ("waiting", None) for k, _, _ in steps}
    icons = {"waiting": "○", "running": "◌", "done": "✓", "error": "✕"}
    with st.status(label, expanded=True) as box:
        slot = st.empty()
        while worker.is_alive() or not events.empty():
            while not events.empty():
                n, s, t = events.get()
                state[n] = (s, t)
            slot.markdown("".join(
                f'<div class="ba-step">{icons[state[k][0]]} <b>{name}</b> <span class="who">{who}</span>'
                f'<span class="t">{"" if state[k][1] is None else f"{state[k][1]:.1f}s"}</span></div>'
                for k, name, who in steps), unsafe_allow_html=True)
            time.sleep(0.2)
        if "error" in out:
            box.update(label="Stopped", state="error")
        else:
            box.update(label="Done", state="complete", expanded=False)

    err = out.get("error")
    if isinstance(err, AuditFailed):
        st.error(f"**Couldn't audit this code** ({err.stage}): {err}")
        if err.details:
            with st.expander("Details"):
                st.code(err.details[-1500:])
        return None
    if err is not None:
        st.error(f"Something went wrong: {type(err).__name__}: {err}")
        return None
    return out["result"]


def run_live(source: str, prices: pd.DataFrame) -> dict | None:
    return run_with_progress("Auditing your strategy…", STEPS,
                             lambda on_step: run_full_audit(source, prices, on_step=on_step))


# ---------- the report ----------

def render_banner(result: dict):
    overall = result["evidence"]["overall"]
    color, icon, label = status_html(overall)
    headline = html.escape(result["report"]["headline"])
    st.markdown(f'<div class="ba-banner" style="--ba-c:{color}"><div class="ba-label">{icon}{label}</div>'
                f'<div class="ba-head">{headline}</div></div>', unsafe_allow_html=True)


def render_metrics(result: dict):
    m = result["evidence"]["reported_metrics"]
    shift = next(t for t in result["evidence"]["tests"] if t["test"] == "signal_shift")["metrics"]
    c = st.columns(4)
    c[0].metric("Reported yearly return", f"{m['cagr']:.1%}")
    c[1].metric("Reported Sharpe", f"{m['sharpe']:.2f}")
    c[2].metric("Worst drawdown", f"{m['max_drawdown']:.1%}")
    c[3].metric("Sharpe when trades are delayed", f"{shift['sharpe_shifted']:.2f}",
                delta=f"{shift['sharpe_shifted'] - shift['sharpe_original']:+.2f}", delta_color="off",
                help=f"Every trade delayed by {shift.get('delay', '1 bar')}.")


def _log_ticks(lo: float, hi: float) -> list[float]:
    """Clean dollar ticks (…, 0.5, 1, 2, 5, 10, …) covering [lo, hi]."""
    for steps in ((1, 2, 5), (1, 1.5, 2, 3, 5, 7), (1, 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.8, 2, 2.5, 3, 4, 5, 6, 8)):
        ticks, mag = [], 10.0 ** (int(f"{lo:e}".split("e")[1]) - 1)
        while mag <= hi * 10:
            ticks += [round(m * mag, 10) for m in steps if lo * 0.9 <= m * mag <= hi * 1.1]
            mag *= 10
        if len(ticks) >= 3:
            break
    return ticks


def render_chart(result: dict):
    curves = result["curves"]
    equity_chart(curves["dates"], ("Reported", f"Trades delayed {curves.get('delay', '1 bar')}"),
                 curves["original"], curves["shifted"])


def equity_chart(dates: list, names: tuple, first: list, second: list):
    """Two equity curves on a log scale (categorical slots 1-2), with hover, end labels and a table view."""
    df = pd.DataFrame({"date": pd.to_datetime(dates), names[0]: first, names[1]: second})
    long = df.melt("date", var_name="series", value_name="equity")
    mode = "dark" if getattr(st.context.theme, "type", "light") == "dark" else "light"
    colors = SERIES[mode]
    ink, muted, grid = ("#ffffff", "#c3c2b7", "#2f2f2d") if mode == "dark" else ("#0b0b0b", "#52514e", "#e7e6e2")
    lo, hi = float(long["equity"].min()), float(long["equity"].max())
    yscale = alt.Scale(type="log", domain=[lo * 0.9, hi * 1.1], nice=False)

    color = alt.Color("series:N", scale=alt.Scale(domain=list(names), range=list(colors)),
                      legend=alt.Legend(orient="top", title=None, labelColor=ink, labelLimit=0, symbolStrokeWidth=3))
    base = alt.Chart(long).encode(
        x=alt.X("date:T", title=None, axis=alt.Axis(grid=False, format="%Y", tickCount="year", labelColor=muted,
                                                    domainColor=grid, tickColor=grid)),
        y=alt.Y("equity:Q", title="Growth of $1 (log scale)", scale=yscale,
                axis=alt.Axis(values=_log_ticks(lo, hi), format="$,.2~f", gridColor=grid, labelColor=muted,
                              titleColor=muted, domain=False, ticks=False)),
        color=color,
    )
    lines = base.mark_line(strokeWidth=2)
    hover = alt.selection_point(fields=["date"], nearest=True, on="pointerover", empty=False, clear="pointerout")
    rule = alt.Chart(df).mark_rule(color=muted, strokeWidth=1).encode(
        x="date:T", opacity=alt.condition(hover, alt.value(0.6), alt.value(0)),
        tooltip=[alt.Tooltip("date:T", title="Date"),
                 alt.Tooltip(f"{names[0]}:Q", title=names[0], format="$,.2f"),
                 alt.Tooltip(f"{names[1]}:Q", title=names[1], format="$,.2f")],
    ).add_params(hover)
    dots = base.mark_point(size=60, filled=True, stroke="white", strokeWidth=2).encode(
        opacity=alt.condition(hover, alt.value(1), alt.value(0))).transform_filter(hover)
    # End labels: the higher line's label goes up, the lower one's goes down, so close values never overlap.
    last = long[long["date"] == long["date"].max()].sort_values("equity").reset_index(drop=True)
    labels = alt.layer(*[
        alt.Chart(last.iloc[[i]]).mark_text(align="left", dx=6, dy=dy, fontWeight=600, color=ink).encode(
            x="date:T", y=alt.Y("equity:Q", scale=yscale), text=alt.Text("equity:Q", format="$,.2f"))
        for i, dy in zip(range(len(last)), (9, -9) if len(last) == 2 else (0,) * len(last))
    ])
    chart = (lines + rule + dots + labels).properties(height=340, padding={"right": 64, "top": 18}) \
        .configure_view(stroke=None)
    st.altair_chart(chart, width="stretch", theme=None)
    with st.expander("Chart data as a table"):
        weekly = df.set_index("date").resample("W").last().round(3)
        st.dataframe(weekly, width="stretch")


def render_cards(result: dict):
    explained = {t["test"]: t for t in result["report"]["tests"]}
    cols = st.columns(len(TESTS))
    for col, t in zip(cols, result["evidence"]["tests"]):
        name, what = TESTS.get(t["test"], (t["test"], ""))
        color, icon, label = status_html(t["verdict"])
        why = html.escape(explained.get(t["test"], {}).get("explanation", t["summary"]))
        col.markdown(f'<div class="ba-card" style="--ba-c:{color}"><div>{icon}<b>{label}</b></div>'
                     f'<h4>{name}</h4><div class="ba-what">{what}</div><div class="ba-why">{why}</div>'
                     f'<div class="ba-raw">Test output: {html.escape(t["summary"])}</div></div>',
                     unsafe_allow_html=True)


def flagged_lines(result: dict) -> dict[int, list[str]]:
    notes: dict[int, list[str]] = {}
    reviews = {(r["line"], r["rule"]): r for r in result["plan"].get("scan_review", [])}
    for f in result["plan"].get("findings", []):
        notes.setdefault(f["line"], []).append(f"**{f['concern'].capitalize()}** (Nemotron Super): {f['explanation']}")
    for h in result.get("static_hits", []):
        review = reviews.get((h["line"], h["rule"]))
        if review and review["verdict"] == "dismissed":
            continue
        notes.setdefault(h["line"], []).append(f"**Rule `{h['rule']}`** ({'Nemotron Nano' if h.get('explained_by', 'rule') != 'rule' else 'rule'}): "
                                               f"{h.get('explanation', '')}")
    return notes


def render_code(result: dict):
    notes = flagged_lines(result)
    fixes = drop_noop_fixes(result["report"].get("fixes", []), result["source"])
    rows, blank_run = [], 0
    lines = result["source"].splitlines()
    for i, line in enumerate(lines + [None], start=1):  # sentinel flushes a trailing blank run
        if line is not None and not line.strip() and i not in notes:
            blank_run += 1
            continue
        if blank_run:  # collapse removed comments/docstrings; keep real line numbers
            rows.append("<tr><td class='ln'>⋯</td><td> </td></tr>" if blank_run > 1
                        else f"<tr><td class='ln'>{i - 1}</td><td> </td></tr>")
            blank_run = 0
        if line is None:
            break
        cls = ' class="hit"' if i in notes else ""
        rows.append(f"<tr{cls}><td class='ln'>{i}</td><td>{html.escape(line) or ' '}</td></tr>")
    left, right = st.columns([3, 2])
    left.markdown(f'<div class="ba-code"><table>{"".join(rows)}</table></div>', unsafe_allow_html=True)
    with right:
        if not notes and not fixes:
            st.success("No suspicious lines found.")
        for line in sorted(notes):
            st.markdown(f"**Line {line}**")
            for n in notes[line]:
                st.markdown(f"- {n}")
        if fixes:
            st.markdown("**Suggested fixes**")
            for f in fixes:
                st.markdown(f"- Line {f['line']}: {f['fix']}")
    st.caption("Comments and docstrings are removed before the AI reads the code, so it can't be tipped off by them.")


def render_how(result: dict):
    with st.expander("How this audit was checked"):
        st.markdown("**Pipeline**")
        render_steps(result.get("timings", {}))
        st.markdown("Tests run first in an isolated Token Factory Sandbox; AI calls only start once they succeed. "
                    "The AI explains, the tests decide: every verdict below comes from the tests.")

        plan, actual = result["plan"], {t["test"]: t["verdict"] for t in result["evidence"]["tests"]}
        st.markdown("**Nemotron Super predicted each result before the tests ran**")
        pred = pd.DataFrame([{"Test": TESTS.get(p["test"], (p["test"],))[0], "Predicted": p["expected_verdict"],
                              "Actual": actual.get(p["test"], "?"),
                              "Match": "✓" if p["expected_verdict"] == actual.get(p["test"]) else "✗",
                              "Reasoning": p["hypothesis"]} for p in plan.get("test_plan", [])])
        if not pred.empty:
            st.dataframe(pred, hide_index=True, width="stretch")

        hits = result.get("static_hits", [])
        if hits:
            st.markdown("**Rule hits, explained by Nemotron Nano and reviewed by Nemotron Super**")
            reviews = {(r["line"], r["rule"]): r for r in plan.get("scan_review", [])}
            st.dataframe(pd.DataFrame([{
                "Line": h["line"], "Rule": h["rule"], "Explanation": h.get("explanation", ""),
                "Super's review": (reviews.get((h["line"], h["rule"])) or {}).get("verdict", "—"),
                "Reason": (reviews.get((h["line"], h["rule"])) or {}).get("reason", ""),
            } for h in hits]), hide_index=True, width="stretch")

        rep = result["report"]
        st.markdown("**Guardrails**")
        st.markdown(
            f"- Plan attempts: {plan.get('attempts', 1)}{' (still incomplete)' if plan.get('incomplete') else ''}\n"
            f"- AI verdicts corrected to match the tests: {len(rep.get('verdicts_overridden', []))}\n"
            f"- Numbers in the report not found in the test results: "
            f"{', '.join(rep.get('unverified_numbers', [])) or 'none'}\n"
            f"- AI-cited lines rejected for not matching the code: {len(plan.get('rejected_findings', []))}")
        st.download_button("Download full audit (JSON)", json.dumps(result, indent=1),
                           file_name="backtest_audit.json", mime="application/json")


def _verdicts(ev: dict) -> dict:
    return {t["test"]: t["verdict"] for t in ev["tests"]}


def render_fix_result(fix: dict, before: dict, source: str, key: str):
    attempts = fix["attempts"]
    for a in attempts:
        color, icon, _ = status_html("PASS" if a["accepted"] else "FAIL")
        why = "all tests pass" if a["accepted"] else "; ".join(a["problems"])
        st.markdown(f'<div class="ba-attempt">{icon}<span>Round {a["round"]}: <b>{html.escape(a["approach"])}</b>'
                    f'</span><span class="why">{html.escape(why)}</span></div>', unsafe_allow_html=True)
    if fix["accepted"] is None:
        st.warning(f"No fix passed every test after {max(a['round'] for a in attempts)} rounds. "
                   "The failures above show what still uses future information.")
        return
    best = attempts[fix["accepted"]]
    st.success(f"**Fixed and proven:** {best['explanation']}")

    after = best["evidence"]
    bm, am = before["reported_metrics"], after["reported_metrics"]
    bv, av = _verdicts(before), _verdicts(after)
    rows = [("Yearly return", f"{bm['cagr']:.1%}", f"{am['cagr']:.1%}"),
            ("Sharpe", f"{bm['sharpe']:.2f}", f"{am['sharpe']:.2f}")]
    rows += [(TESTS[t][0], bv.get(t, "?"), av.get(t, "?")) for t in TESTS]
    if am.get("exposure") is not None and bm.get("exposure") is not None:
        rows.append(("In the market", f"{bm['exposure']:.0%}", f"{am['exposure']:.0%}"))
    left, right = st.columns([2, 3])
    left.markdown("**Before vs. after** (numbers from the sandbox, not the AI)")
    left.dataframe(pd.DataFrame(rows, columns=["", "Original", "Fixed"]), hide_index=True, width="stretch")
    with right:
        st.markdown("**What changed**")
        cls = lambda ln: "add" if ln.startswith("+") else "del" if ln.startswith("-") else "hunk" if ln.startswith("@@") else ""  # noqa: E731
        body = "".join(f'<div class="{cls(ln)}">{html.escape(ln) or " "}</div>'
                       for ln in diff_lines(source, best["code"]) if not ln.startswith(("+++", "---")))
        st.markdown(f'<div class="ba-diff">{body}</div>', unsafe_allow_html=True)
        st.download_button("Download fixed strategy", best["code"], file_name="fixed_strategy.py",
                           mime="text/x-python", key=f"dl_{key}")
    if best.get("curves") and before.get("curves"):
        st.markdown("**Original reported equity vs. the fixed strategy**")
        equity_chart(before["curves"]["dates"], ("Original (as reported)", "Fixed (honest)"),
                     before["curves"]["original"], best["curves"]["original"])
    st.caption(f"{len(attempts)} candidate fix(es) tested in parallel branches of one sandbox snapshot "
               f"in {fix.get('seconds', 0):.0f}s. A fix counts only if the delay and hide-the-future tests pass, "
               "nothing else fails, and the strategy still trades.")


def render_fix(result: dict, prices: pd.DataFrame, key: str):
    st.markdown("##### 🛠 Fix it: Nemotron rewrites the code, the sandbox proves it")
    ok, reason = eligibility(result["evidence"], result["plan"])
    if not ok:
        st.info(reason)
        return
    fix = st.session_state.get(key) or result.get("fix")
    before = {**result["evidence"], "curves": result["curves"]}
    if fix is None:
        st.caption("Nemotron Super writes two minimal fixes; each runs all four tests in its own branch of a "
                   "sandbox snapshot. If neither passes, it tries again with the failures as feedback.")
        if live_button("Fix it", result["source"], key=f"btn_{key}"):
            fix = run_with_progress("Fixing the strategy…", FIX_STEPS, lambda on_step: fix_strategy(
                result["source"], result["evidence"], result["plan"], prices, on_step=on_step))
            if fix:
                st.session_state[key] = fix
    if fix:
        if key not in st.session_state:
            st.caption(f"Saved fix from {result.get('generated_at', 'an earlier run')}.")
        render_fix_result(fix, before, result["source"], key)


def render_report(result: dict, prices: pd.DataFrame | None = None, fix_key: str = "fix"):
    render_banner(result)
    render_metrics(result)
    st.markdown("##### Reported results vs. the same trades delayed")
    st.caption("If a strategy only works when it trades instantly, it was probably using information it couldn't "
               "have had. Honest strategies barely change when delayed.")
    render_chart(result)
    st.markdown("##### The four tests")
    render_cards(result)
    st.markdown("##### Where in the code")
    render_code(result)
    if prices is not None:
        render_fix(result, prices, fix_key)
    render_how(result)
    caveats = result["report"].get("caveats")
    if caveats:
        st.caption(caveats)


# ---------- page ----------

def live_button(label: str, code: str, key: str, note=None) -> bool:
    """Gated live-run button. `note`: where to show why it's disabled (defaults to right below it)."""
    runs = st.session_state.setdefault("live_runs", 0)
    decision = check_live_run(runs, code)
    clicked = st.button(label, key=key, type="primary", disabled=not decision.allowed,
                        help=None if decision.allowed else decision.reason)
    if not decision.allowed:
        (note or st).caption(decision.reason)
    if clicked:
        if not reserve_live_run():
            st.warning("Today's live audits for this demo are used up. Try again tomorrow.")
            return False
        st.session_state["live_runs"] = runs + 1
        return True
    return False


HERO = """
<div class="ba-hero">
  <h1>Is your backtest lying?</h1>
  <div class="pitch">Paste a trading strategy. We run it in an isolated Nebius sandbox, attack it four ways, and
  NVIDIA Nemotron explains, and fixes, what's wrong. Every verdict comes from the tests, never from the AI.</div>
  <div class="ba-steps">
    <div class="s"><span class="n">1</span><span class="t">Scan</span>
      <div class="d">Rules flag known leak patterns. No AI, instant.</div></div>
    <div class="s"><span class="n">2</span><span class="t">Attack</span>
      <div class="d">4 tests run on the strategy in a Token Factory Sandbox.</div></div>
    <div class="s"><span class="n">3</span><span class="t">Explain</span>
      <div class="d">Nemotron Super reads the code and the evidence; Nano explains rule hits.</div></div>
    <div class="s"><span class="n">4</span><span class="t">Fix</span>
      <div class="d">Nemotron writes fixes; parallel sandbox branches prove which one works.</div></div>
  </div>
  <div class="ba-built">Built with Nebius Token Factory · Token Factory Sandboxes · NVIDIA Nemotron Super &amp; Nano</div>
</div>
"""
OPTIONS = list(SAMPLES) + [CUSTOM]
PILL_LABELS = {"lookahead": "Lookahead 50%/yr", "leaky": "Leaky", "overfit": "Overfit", "honest": "Honest",
               CUSTOM: "✎ Audit your own code"}


def _pick(widget_key: str):
    value = st.session_state.get(widget_key)
    if value in OPTIONS:  # pills can be clicked off (None): keep the current choice
        st.session_state["choice"] = value


def current_choice() -> str:
    """One choice shared by the main-area pills, the sidebar list and the URL (?strategy=...)."""
    if "choice" not in st.session_state:
        wanted = st.query_params.get("strategy", OPTIONS[0])
        st.session_state["choice"] = wanted if wanted in OPTIONS else OPTIONS[0]
    choice = st.session_state["choice"]
    st.session_state["pick_pills"] = choice
    st.session_state["pick_sidebar"] = choice
    st.query_params["strategy"] = choice
    return choice


def main():
    st.markdown(CSS, unsafe_allow_html=True)
    choice = current_choice()
    with st.sidebar:
        st.markdown("## 🔍 Backtest Auditor")
        st.radio("Strategy", OPTIONS, key="pick_sidebar", on_change=_pick, args=("pick_sidebar",),
                 format_func=lambda k: SAMPLES.get(k, k))
        st.divider()
        st.caption("⚠️ Educational tool, not financial advice. Sample data is synthetic (random), so no strategy "
                   "has a real edge on it.")

    st.markdown(HERO, unsafe_allow_html=True)
    st.pills("Try an example", OPTIONS, key="pick_pills", on_change=_pick, args=("pick_pills",),
             format_func=lambda k: PILL_LABELS[k])

    if choice != CUSTOM:
        result = load_sample(choice)
        st.markdown(f"### {SAMPLES[choice]}")
        if result is None:
            st.warning("This sample's saved audit is missing. Run `python -m scripts.precompute_samples`.")
            return
        st.caption(result.get("description", ""))
        live_key = f"live_{choice}"
        pipe, btn = st.columns([4, 1], vertical_alignment="top")
        note = st.empty()  # full-width line for "why live runs are unavailable"
        with pipe.expander("Audit pipeline and timings", expanded=False):
            render_steps(result.get("timings", {}), result.get("generated_at"))
        with btn:
            rerun = live_button("Re-run live", result["source"], key=f"btn_{choice}", note=note)
        if rerun:
            from strategies import STRATEGIES
            from agent.pipeline import sample_source
            live = run_live(sample_source(STRATEGIES[choice]), default_prices(result.get("seed", 7)))
            if live:
                st.session_state[live_key] = live
                st.session_state.pop(f"fix_{choice}_live", None)
        shown = st.session_state.get(live_key, result)
        which = "live" if live_key in st.session_state else "saved"
        render_report(shown, default_prices(result.get("seed", 7)), fix_key=f"fix_{choice}_{which}")
        return

    st.markdown("### Audit your own strategy")
    st.markdown("Write a `run(prices)` function that returns daily positions (0 = cash, 1 = fully long). "
                "Optional: `PARAM_GRID` + `positions_for(prices, **params)` if you searched over settings, "
                "so the overfitting tests can check the search. Your code runs only inside an isolated sandbox.")
    code = st.text_area("Strategy code", TEMPLATE, height=320, label_visibility="collapsed")
    c1, c2 = st.columns([1, 2])
    with c1:
        data = st.radio("Price data", ["Synthetic (random walk)", "Upload CSV"], horizontal=False)
    prices, problem = default_prices(7), ""
    with c2:
        if data == "Upload CSV":
            up = st.file_uploader("CSV with a date column and a 'close' column", type=["csv"])
            prices, problem = (parse_prices(up) if up else (None, "Upload a CSV to continue."))
            if problem:
                st.caption(problem)
        else:
            st.caption("10 years of random daily prices. Real edges can't exist here, so great results mean a bug.")
    if prices is not None and live_button("Run audit", code, key="btn_custom"):
        live = run_live(code, prices)
        if live:
            st.session_state["live_custom"] = live
            st.session_state["live_custom_prices"] = prices
            st.session_state.pop("fix_custom", None)
    if "live_custom" in st.session_state:
        render_report(st.session_state["live_custom"], st.session_state["live_custom_prices"], fix_key="fix_custom")


main()
