"""Static scan rules, the Nano explainer's fallback, and chat_json's quirk handling.

Offline except the opt-in Nano test (RUN_LLM_TESTS=1 pytest -q -m llm).
"""
import inspect
import os
from types import SimpleNamespace

import pytest

import agent.llm as llm
import agent.scanner as scanner
from agent.sanitize import strip_hints
from agent.scanner import explain_hits, static_scan
from strategies import STRATEGIES


def rules(code: str) -> set[str]:
    return {h["rule"] for h in static_scan(code)}


@pytest.mark.parametrize("code, rule", [
    ("x = c.rolling(5, center=True).mean()", "centered_window"),
    ("x = c.shift(-1)", "negative_shift"),
    ("x = c.shift(periods=-2)", "negative_shift"),
    ("x = c.bfill()", "backfill"),
    ("x = c.fillna(method='bfill')", "backfill"),
    ("x = c.interpolate(limit_direction='both')", "backfill"),
    ("x = (c - c.mean()) / c.std()", "full_sample_stat"),
    ("x = np.mean(c)", "full_sample_stat"),
    ("x = c.rank(pct=True)", "full_sample_stat"),
    ("m = model.fit(X, y)", "full_sample_fit"),
    ("x = c.iloc[i + 1]", "future_index"),
])
def test_rule_fires(code, rule):
    assert rule in rules(code)


@pytest.mark.parametrize("code", [
    "x = c.rolling(5, center=False).mean()",
    "x = c.rolling(5).mean()",
    "x = c.shift(1)",
    "x = c.ffill()",
    "x = c.rolling(20).std()",
    "x = c.expanding().max()",
    "x = c.rolling(20).rank()",
    "x = c.ewm(span=10).mean()",
    "x = c.iloc[i - 1]",
    "x = c.iloc[: i + 1]",
    "# c.rolling(5, center=True) in a comment",
    "s = 'c.shift(-1) in a string'",
])
def test_rule_stays_quiet(code):
    assert rules(code) == set()


def test_samples():
    found = {name: [(h["line"], h["rule"]) for h in static_scan(strip_hints(inspect.getsource(m)))]
             for name, m in STRATEGIES.items()}
    # Only the syntactic bug is a rule hit; lookahead/overfit are semantic and left to the planner.
    assert found == {"honest": [], "lookahead": [], "leaky": [(19, "centered_window")], "overfit": []}


def test_hit_snippets_are_on_their_lines():
    code = "a = 1\nb = c.shift(-1)\nd = c.rolling(3, center=True).mean().bfill()\n"
    lines = code.splitlines()
    for h in static_scan(code):
        assert h["snippet"] == lines[h["line"] - 1].strip()
    assert [(h["line"], h["rule"]) for h in static_scan(code)] == [(2, "negative_shift"), (3, "backfill"),
                                                                   (3, "centered_window")]


def test_explain_falls_back_to_rule_text_when_nano_fails(monkeypatch):
    def boom(*a, **k):
        raise llm.LLMJSONError("no JSON")
    monkeypatch.setattr(scanner, "chat_json", boom)
    hits = explain_hits(static_scan("x = c.shift(-1)"))
    assert hits[0]["explained_by"] == "rule" and hits[0]["explanation"] == scanner.RULES["negative_shift"][2]


def test_explain_ignores_bad_ids(monkeypatch):
    monkeypatch.setattr(scanner, "chat_json", lambda *a, **k: {"explanations": [{"id": 7, "text": "x"},
                                                                               {"id": 0, "text": "Pulls tomorrow."}]})
    hits = explain_hits(static_scan("x = c.shift(-1)"))
    assert hits[0]["explanation"] == "Pulls tomorrow." and hits[0]["explained_by"] != "rule"


def test_chat_json_reads_reasoning_when_content_is_empty(monkeypatch):
    reply = llm.ChatReply(content="", reasoning='{"hits": []}', raw=SimpleNamespace())
    monkeypatch.setattr(llm, "chat", lambda *a, **k: reply)
    assert llm.chat_json([], model="m", schema={}, name="x") == {"hits": []}


def test_chat_json_retries_then_raises(monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "chat", lambda *a, **k: calls.append(1) or llm.ChatReply("not json", None, None))
    with pytest.raises(llm.LLMJSONError):
        llm.chat_json([], model="m", schema={}, name="x", retries=1)
    assert len(calls) == 2


@pytest.mark.llm
@pytest.mark.skipif(os.getenv("RUN_LLM_TESTS") != "1", reason="set RUN_LLM_TESTS=1")
def test_nano_explains_without_calling_code_safe():
    hits = explain_hits(static_scan("z = (r - r.mean()) / r.std()\nn = c.shift(-1)\n"))
    for h in hits:
        assert h["explanation"]
        assert not any(w in h["explanation"].lower() for w in ("no leakage", "is safe", "no future"))
