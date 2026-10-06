"""The three Streamlit pages render without errors, saved samples show up, and live runs stay off by default.

Runs the real app headlessly (streamlit.testing); no network or paid calls.
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py")
SAMPLES = ["lookahead", "leaky", "overfit", "next_day", "weekly", "zscore", "honest", "honest_rsi"]


def _app(page: str | None = None, **params) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    for k, v in params.items():
        at.query_params[k] = v
    at.run()
    if page:
        at.switch_page(page).run()
    return at


def test_home_landing_page(monkeypatch):
    monkeypatch.delenv("LIVE_RUNS_ENABLED", raising=False)
    at = _app()
    assert not at.exception, [e.value for e in at.exception]
    assert any("Is your backtest lying?" in m.value for m in at.markdown)
    cards = [m.value for m in at.markdown if "class=\"ba-gcard\"" in m.value]
    assert len(cards) == len(SAMPLES)                                # one gallery card per saved sample
    assert sum("Caught" in c for c in cards) == 6 and sum("Honest" in c for c in cards) == 2


@pytest.mark.parametrize("name", SAMPLES)
def test_example_pages_render(name, monkeypatch):
    monkeypatch.delenv("LIVE_RUNS_ENABLED", raising=False)
    at = AppTest.from_file(APP, default_timeout=60).run()
    at.query_params["strategy"] = name
    at.switch_page("examples.py").run()
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.metric) == 4
    assert all(b.disabled for b in at.button if "live" in b.label.lower())   # no paid calls from the public page


def test_lookahead_example_tells_the_story():
    at = _app("examples.py", strategy="lookahead")
    values = {m.label: m.value for m in at.metric}
    assert values["Reported Sharpe"] == "3.43" and values["Sharpe when trades are delayed"] == "0.14"


def test_legacy_deep_link_goes_to_examples():
    at = _app(strategy="weekly")                                     # old URL: /?strategy=weekly
    assert not at.exception
    assert any(m.value == "### Weekly trend: Monday knows Friday" for m in at.markdown)


def test_example_pills_switch_strategy():
    at = _app("examples.py", strategy="lookahead")
    at.session_state["example_pills"] = "zscore"
    at.session_state["example"] = "zscore"
    at.run()
    assert not at.exception and any(m.value == "### Z-score: normalized with the future" for m in at.markdown)


def test_audit_page_renders_with_run_disabled(monkeypatch):
    monkeypatch.delenv("LIVE_RUNS_ENABLED", raising=False)
    at = _app("audit.py")
    assert not at.exception, [e.value for e in at.exception]
    assert at.text_area(key="custom_code").value.startswith("import pandas")
    assert any("How to write a strategy" in m.value for m in at.markdown)
    assert [b.disabled for b in at.button if b.label == "Run audit"] == [True]


def test_start_from_example_loads_code_without_hints():
    at = _app("audit.py")
    at.selectbox(key="starter").set_value("lookahead").run()
    code = at.text_area(key="custom_code").value
    assert not at.exception and "def run(" in code and "signal = (c > sma)" in code
    assert "BUG" not in code and "PLANTED_BUG" not in code and "\n\n\n" not in code
