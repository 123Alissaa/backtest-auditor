"""Cost guards: live runs must be off by default and every cap must hold."""
from dataclasses import replace

from agent.config import Settings
from agent.limits import check_live_run, reserve_live_run, runs_today

ON = replace(Settings(), live_runs_enabled=True, live_runs_until="2099-01-01", daily_live_run_cap=2,
             session_live_run_cap=3, max_code_bytes=100, judging_from="2099-01-01", judging_until="2099-01-02")


def test_live_runs_off_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("LIVE_RUNS_ENABLED", raising=False)
    assert Settings().live_runs_enabled is False
    assert not check_live_run(0, cfg=replace(ON, live_runs_enabled=False), path=tmp_path / "c.json").allowed


def test_allowed_when_on_and_under_caps(tmp_path):
    assert check_live_run(0, "x = 1", cfg=ON, path=tmp_path / "c.json").allowed


def test_each_cap_blocks(tmp_path):
    path = tmp_path / "c.json"
    assert not check_live_run(0, cfg=replace(ON, live_runs_until="2020-01-01"), path=path).allowed   # past cut-off
    assert not check_live_run(0, "x" * 101, cfg=ON, path=path).allowed                                 # code too big
    assert not check_live_run(3, cfg=ON, path=path).allowed                                            # session cap
    assert reserve_live_run(cfg=ON, path=path) and reserve_live_run(cfg=ON, path=path)
    assert runs_today(path) == 2
    assert not reserve_live_run(cfg=ON, path=path)                                                     # daily cap
    assert not check_live_run(0, cfg=ON, path=path).allowed


def test_counter_resets_on_a_new_day(tmp_path):
    path = tmp_path / "c.json"
    path.write_text('{"day": "2000-01-01", "count": 99}')
    assert runs_today(path) == 0 and check_live_run(0, cfg=ON, path=path).allowed


def test_corrupt_counter_file_does_not_crash(tmp_path):
    path = tmp_path / "c.json"
    path.write_text("not json")
    assert runs_today(path) == 0


def test_spend_budget_blocks_new_runs(tmp_path):
    from agent.limits import record_spend, spend_today
    path, cfg = tmp_path / "c.json", replace(ON, daily_live_run_cap=100, daily_budget_usd=0.05)
    assert reserve_live_run(cfg=cfg, path=path)
    record_spend(0.03, path=path)
    assert check_live_run(0, cfg=cfg, path=path).allowed
    record_spend(0.025, path=path)                                   # now 0.055 >= 0.05
    assert round(spend_today(path), 3) == 0.055
    assert not check_live_run(0, cfg=cfg, path=path).allowed and not reserve_live_run(cfg=cfg, path=path)


def test_prices_match_catalog_and_unknown_models_are_priced_high():
    from agent.limits import price_of
    assert round(price_of("nvidia/nemotron-3-super-120b-a12b", 1_000_000, 1_000_000), 2) == 1.20
    assert round(price_of("nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", 1_000_000, 0), 2) == 0.06
    assert price_of("some/new-model", 1_000_000, 1_000_000) == 4.0          # Ultra prices: errs on the safe side


def test_chat_records_measured_spend(tmp_path, monkeypatch):
    from types import SimpleNamespace
    import agent.limits as limits
    import agent.llm as llm
    monkeypatch.setattr(limits, "COUNTER_FILE", tmp_path / "c.json")
    monkeypatch.setattr(limits.record_spend, "__defaults__", (tmp_path / "c.json",))
    resp = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=10_000, completion_tokens=2_000),
                           choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))])
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **k: resp)))
    monkeypatch.setattr(llm, "get_client", lambda: fake)
    llm.chat([], model="nvidia/nemotron-3-super-120b-a12b")
    assert round(limits.spend_today(tmp_path / "c.json"), 6) == round((10_000 * 0.30 + 2_000 * 0.90) / 1e6, 6)



def test_judging_window_raises_caps_and_worst_case_stays_under_credit():
    from datetime import date, timedelta
    from agent.limits import caps_for
    cfg = Settings()
    before, during, after = date(2026, 11, 30), date(2026, 12, 8), date(2026, 12, 16)
    assert caps_for(before, cfg).budget_usd == 0.15 and caps_for(before, cfg).session_runs == 3
    assert caps_for(during, cfg).budget_usd == 0.75 and caps_for(during, cfg).daily_runs == 100
    assert caps_for(during, cfg).session_runs == 5 and caps_for(after, cfg).budget_usd == 0.15
    start, end = date(2026, 10, 6), date.fromisoformat(cfg.live_runs_until)
    worst = sum(caps_for(start + timedelta(d), cfg).budget_usd for d in range((end - start).days + 1))
    assert worst < 22, worst                          # remaining credit ~$24.5: the balance can't go negative
