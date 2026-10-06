"""Audit your code: paste or load a strategy, audit it live in the sandbox, then fix it."""
import streamlit as st

import ui

st.markdown("### Audit your own strategy")
st.session_state.setdefault("custom_code", ui.TEMPLATE)
st.selectbox("Start from", list(ui.STARTERS), key="starter", format_func=lambda k: ui.STARTERS[k],
             on_change=ui._load_starter,
             help="Load one of the examples (comments removed), audit it, then edit the bug away and re-run.")
editor, guide = st.columns([3, 2])
with editor:
    code = st.text_area("Strategy code", key="custom_code", height=380, label_visibility="collapsed")
with guide:
    st.markdown(ui.GUIDE)

c1, c2 = st.columns([1, 2])
with c1:
    data = st.radio("Price data", ["Synthetic (random walk)", "Upload CSV"], horizontal=False)
prices, problem = ui.default_prices(7), ""
with c2:
    if data == "Upload CSV":
        up = st.file_uploader("CSV with a date column and a 'close' column", type=["csv"])
        prices, problem = (ui.parse_prices(up) if up else (None, "Upload a CSV to continue."))
        if problem:
            st.caption(problem)
    else:
        st.caption("10 years of random daily prices. Real edges can't exist here, so great results mean a bug.")

if prices is not None and ui.live_button("Run audit", code, key="btn_custom"):
    live = ui.run_live(code, prices)
    if live:
        st.session_state["live_custom"] = live
        st.session_state["live_custom_prices"] = prices
        st.session_state.pop("fix_custom", None)
if "live_custom" in st.session_state:
    ui.render_report(st.session_state["live_custom"], st.session_state["live_custom_prices"], fix_key="fix_custom")
st.markdown(ui.FOOTER, unsafe_allow_html=True)
