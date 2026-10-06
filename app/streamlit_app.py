"""Backtest Auditor web app (Streamlit): router for the three pages.

    streamlit run app/streamlit_app.py

Pages: Home (landing page), Examples (saved audits of 8 strategies), Audit your code.
Saved audits come from app/samples/*.json (scripts/precompute_samples.py), so browsing
makes no paid calls. Live audits are OFF unless LIVE_RUNS_ENABLED=true and are capped
(agent/limits.py). User code is never executed here: only parsed, or sent to a Token
Factory Sandbox.
"""
import os
import sys
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="Backtest Auditor", page_icon="🔍", layout="wide")

# Streamlit Cloud keeps secrets in st.secrets; agent.config reads env vars. Bridge before anything imports it.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, (str, int, float, bool)):
            os.environ.setdefault(_k, str(_v))
except Exception:  # no secrets file locally -> .env is used instead
    pass

APP_DIR = Path(__file__).resolve().parent
for path in (APP_DIR, APP_DIR.parent):  # app/ for `import ui`, repo root for agent/, engine/, ...
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import ui  # noqa: E402

st.markdown(ui.CSS, unsafe_allow_html=True)
nav = st.navigation([
    st.Page("home.py", title="Home", icon=":material/home:", default=True),
    st.Page("examples.py", title="Examples", icon=":material/query_stats:", url_path="examples"),
    st.Page("audit.py", title="Audit your code", icon=":material/edit:", url_path="audit"),
], position="top")
nav.run()
