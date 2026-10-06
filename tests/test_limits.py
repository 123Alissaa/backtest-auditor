"""Cost guards: live runs must be off by default and every cap must hold."""
from dataclasses import replace

from agent.config import Settings
from agent.limits import check_live_run, reserve_live_run, runs_today

ON = replace(Settings(), live_runs_enabled=True, live_runs_until="2099-01-01", daily_live_run_cap=2,
             session_live_run_cap=3, max_code_bytes=100)


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
