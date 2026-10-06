"""Examples: saved audits of the 8 sample strategies, each re-runnable live."""
import streamlit as st

import ui

NAMES = list(ui.SAMPLES)
PILLS = {"lookahead": "Lookahead 50%/yr", "leaky": "Leaky", "overfit": "Overfit", "next_day": "shift(-1) slip",
         "weekly": "Weekly bfill", "zscore": "Full-history z-score", "honest": "Honest SMA",
         "honest_rsi": "Honest RSI"}


def _picked():
    if st.session_state.get("example_pills") in NAMES:  # pills can be clicked off (None): keep the choice
        st.session_state["example"] = st.session_state["example_pills"]


wanted = st.query_params.get("strategy")
if wanted in NAMES and wanted != st.session_state.get("example_from_url"):
    st.session_state["example"] = st.session_state["example_from_url"] = wanted  # a new deep link wins
st.session_state.setdefault("example", NAMES[0])
choice = st.session_state["example"]
st.session_state["example_pills"] = choice
st.query_params["strategy"] = choice

st.pills("Classic bugs · real-world mistakes · honest strategies", NAMES, key="example_pills", on_change=_picked,
         format_func=lambda k: PILLS[k])

result = ui.load_sample(choice)
st.markdown(f"### {ui.SAMPLES[choice]}")
if result is None:
    st.warning("This sample's saved audit is missing. Run `python -m scripts.precompute_samples`.")
    st.stop()
st.caption(result.get("description", ""))

live_key = f"live_{choice}"
pipe, btn = st.columns([4, 1], vertical_alignment="top")
note = st.empty()  # full-width line for "why live runs are unavailable"
with pipe.expander("Audit pipeline and timings", expanded=False):
    ui.render_steps(result.get("timings", {}), result.get("generated_at"))
with btn:
    rerun = ui.live_button("Re-run live", result["source"], key=f"btn_{choice}", note=note)
if rerun:
    from agent.pipeline import sample_source
    from strategies import STRATEGIES
    live = ui.run_live(sample_source(STRATEGIES[choice]), ui.default_prices(result.get("seed", 7)))
    if live:
        st.session_state[live_key] = live
        st.session_state.pop(f"fix_{choice}_live", None)
shown = st.session_state.get(live_key, result)
which = "live" if live_key in st.session_state else "saved"
ui.render_report(shown, ui.default_prices(result.get("seed", 7)), fix_key=f"fix_{choice}_{which}")
st.markdown(ui.FOOTER, unsafe_allow_html=True)
