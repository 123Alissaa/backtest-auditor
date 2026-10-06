"""The Streamlit page renders every saved sample without errors, and live runs stay off by default.

Runs the real script headlessly (streamlit.testing); no network or paid calls.
"""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app" / "streamlit_app.py")


def _run(strategy: str) -> AppTest:
    at = AppTest.from_file(APP, default_timeout=60)
    at.query_params["strategy"] = strategy
    return at.run()


@pytest.mark.parametrize("name", ["lookahead", "leaky", "overfit", "next_day", "weekly", "zscore", "honest",
                                  "honest_rsi"])
def test_sample_pages_render(name, monkeypatch):
    monkeypatch.delenv("LIVE_RUNS_ENABLED", raising=False)
    at = _run(name)
    assert not at.exception, [e.value for e in at.exception]
    assert len(at.metric) == 4
    assert all(b.disabled for b in at.button if "live" in b.label.lower())   # no paid calls from the public page


def test_custom_page_renders_with_run_disabled(monkeypatch):
    monkeypatch.delenv("LIVE_RUNS_ENABLED", raising=False)
    at = _run("Your own strategy")
    assert not at.exception, [e.value for e in at.exception]
    assert at.text_area[0].value.startswith("import pandas")
    assert [b.disabled for b in at.button if b.label == "Run audit"] == [True]


def test_lookahead_sample_tells_the_story():
    at = _run("lookahead")
    values = {m.label: m.value for m in at.metric}
    assert values["Reported Sharpe"] == "3.43" and values["Sharpe when trades are delayed"] == "0.14"


def test_hero_and_picker():
    at = _run("lookahead")
    assert any("Is your backtest lying?" in m.value for m in at.markdown)
    at.radio(key="pick_sidebar").set_value("leaky").run()
    assert not at.exception
    assert any(m.value == "### Leaky: smoothed trend" for m in at.markdown)
    assert at.session_state["choice"] == "leaky" and at.query_params["strategy"] in ("leaky", ["leaky"])


def test_unknown_deep_link_falls_back_to_first_sample():
    at = _run("no-such-strategy")
    assert not at.exception and at.session_state["choice"] == "lookahead"
