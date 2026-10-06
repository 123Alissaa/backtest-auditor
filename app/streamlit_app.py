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


def run_live(source: str, prices: pd.DataFrame) -> dict | None:
    """Run the audit in a worker thread; stream step updates from the main thread."""
    events: queue.Queue = queue.Queue()
    out: dict = {}

    def work():
        try:
            out["result"] = run_full_audit(source, prices, on_step=lambda n, s, t: events.put((n, s, t)))
        except Exception as e:  # surfaced below
            out["error"] = e

    worker = threading.Thread(target=work, daemon=True)
    worker.start()
    state = {k: ("waiting", None) for k, _, _ in STEPS}
    with st.status("Auditing your strategy…", expanded=True) as box:
        slot = st.empty()
        while worker.is_alive() or not events.empty():
            while not events.empty():
                n, s, t = events.get()
                state[n] = (s, t)
            icons = {"waiting": "○", "running": "◌", "done": "✓", "error": "✕"}
            slot.markdown("".join(
                f'<div class="ba-step">{icons[state[k][0]]} <b>{name}</b> <span class="who">{who}</span>'
                f'<span class="t">{"" if state[k][1] is None else f"{state[k][1]:.1f}s"}</span></div>'
                for k, name, who in STEPS), unsafe_allow_html=True)
            time.sleep(0.2)
        if "error" in out:
            box.update(label="Audit stopped", state="error")
        else:
            box.update(label="Audit complete", state="complete", expanded=False)

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
    delay = curves.get("delay", "1 bar")
    names = ("Reported", f"Trades delayed {delay}")
    df = pd.DataFrame({"date": pd.to_datetime(curves["dates"]), names[0]: curves["original"],
                       names[1]: curves["shifted"]})
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


def render_report(result: dict):
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
    render_how(result)
    caveats = result["report"].get("caveats")
    if caveats:
        st.caption(caveats)


# ---------- page ----------

def live_button(label: str, code: str, key: str) -> bool:
    runs = st.session_state.setdefault("live_runs", 0)
    decision = check_live_run(runs, code)
    clicked = st.button(label, key=key, type="primary", disabled=not decision.allowed,
                        help=None if decision.allowed else decision.reason)
    if not decision.allowed:
        st.caption(decision.reason)
    if clicked:
        if not reserve_live_run():
            st.warning("Today's live audits for this demo are used up. Try again tomorrow.")
            return False
        st.session_state["live_runs"] = runs + 1
        return True
    return False


def main():
    st.markdown(CSS, unsafe_allow_html=True)
    with st.sidebar:
        st.markdown("## 🔍 Backtest Auditor")
        st.caption("Is your backtest lying? Checks trading-strategy code for lookahead, data leakage and "
                   "overfitting.")
        options = list(SAMPLES) + [CUSTOM]
        wanted = st.query_params.get("strategy", options[0])  # deep links, e.g. ?strategy=leaky
        choice = st.radio("Strategy", options, index=options.index(wanted) if wanted in options else 0,
                          format_func=lambda k: SAMPLES.get(k, k))
        st.query_params["strategy"] = choice
        st.divider()
        with st.expander("How it works"):
            st.markdown(
                "1. **Rules** scan the code for known leak patterns (no AI).\n"
                "2. The strategy runs in an isolated **Nebius Token Factory Sandbox** against four attack tests.\n"
                "3. **NVIDIA Nemotron Nano** explains rule hits; **Nemotron Super** reads the code, predicts the "
                "results and finally explains them.\n"
                "4. Verdicts and numbers always come from the tests, never from the AI.")
        st.caption("⚠️ Educational tool, not financial advice. Sample data is synthetic (random), so no strategy "
                   "has a real edge on it.")

    if choice != CUSTOM:
        result = load_sample(choice)
        st.markdown(f"### {SAMPLES[choice]}")
        if result is None:
            st.warning("This sample's saved audit is missing. Run `python -m scripts.precompute_samples`.")
            return
        st.caption(result.get("description", ""))
        live_key = f"live_{choice}"
        with st.expander("Audit pipeline", expanded=False):
            render_steps(result.get("timings", {}), result.get("generated_at"))
        if live_button("Re-run this audit live", result["source"], key=f"btn_{choice}"):
            from strategies import STRATEGIES
            from agent.pipeline import sample_source
            live = run_live(sample_source(STRATEGIES[choice]), default_prices(result.get("seed", 7)))
            if live:
                st.session_state[live_key] = live
        render_report(st.session_state.get(live_key, result))
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
    if "live_custom" in st.session_state:
        render_report(st.session_state["live_custom"])


main()
