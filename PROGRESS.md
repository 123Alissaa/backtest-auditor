# Progress

_Last updated: Oct 6, 2026_

## Done
- Repo scaffold, CLAUDE.md, requirements checklist, MIT license
- Backtest engine (t → t+1 timing convention) + metrics (CAGR, Sharpe, max drawdown)
- 4 sample strategies on synthetic data: honest, lookahead (~50% CAGR, fake), leaky (centered window), overfit (best of 279 configs)
- Attacks: signal shift, point-in-time, walk-forward, deflated Sharpe ratio
- scripts/run_local_audit.py with reported-vs-delayed equity chart
- Official docs saved to docs/reference/ (local only)
- Token Factory working: Nano + Super model IDs verified live; reasoning fields confirmed in agent/llm.py (`chat_json` handles Nano's empty-content quirk)
- Nemotron planner + interpreter (Super): end to end on all 4 samples (`python -m scripts.audit_with_llm`). Hints stripped before the LLM sees code; cited lines verified; verdicts overwritten with test results; numbers checked against evidence.
- Planner reliability: incomplete/garbled Super plans detected and retried; 8/8 runs flag the right line on lookahead (L17/18), overfit (L36), and nothing on honest.
- Sandboxes (access 2026-10-02): agent/sandbox.py runs all attacks inside a Token Factory Sandbox (`--sandbox`): ~3s per audit (~15s overfit); evidence matches local runs (floats within 1e-9). Crashes, missing run(), syntax errors, SystemExit, timeouts and forged output all handled.
- Scan step: deterministic rules (agent/scanner.py) + Nano one-sentence explanations + Super scan_review (confirm/dismiss). Nano, plan and sandbox tests run in parallel: ~10–28s per audit.
- Signal-shift calendar fix: weekday-only strategies are detected from their positions and delayed one week (same weekday) instead of one bar. Overfit's signal_shift is now PASS (was a false FAIL); lookahead + weekday filter is still caught.
- Report UI (app/streamlit_app.py): sample picker + "your own strategy", verdict banner, metric tiles, reported-vs-delayed equity chart (validated palette, light + dark), four test cards, code view with flagged lines + fixes, "how this was checked" (Super's predictions vs actual, Nano explanations, guardrail counts, JSON download). Deep links: `?strategy=leaky`.
- Shared pipeline (agent/pipeline.py): tests run in the sandbox FIRST, paid LLM calls only after they succeed.
- Cost guards (agent/limits.py): live runs OFF unless LIVE_RUNS_ENABLED=true; when on: measured LLM spend budget $0.20/day (token usage x catalog prices: Super $0.30/$0.90, Nano $0.06/$0.24 per M), 30 runs/day global, 3/session, 20 KB code, cut-off 2026-12-15. Worst case $0.20 x ~70 days = $14 < remaining credit. A live audit measured $0.0027 and 15s (Oct 6). Samples are saved audits (app/samples/*.json, `python -m scripts.precompute_samples`), so viewing the demo makes no paid calls. Total Token Factory spend so far: ~$0.31 (Oct 6).
- Tests: 71 offline + 7 opt-in (`RUN_SANDBOX_TESTS=1 pytest -m sandbox`, `RUN_LLM_TESTS=1 pytest -m llm`)

- Deployed 2026-10-06: https://backtest-auditor.streamlit.app (Streamlit Community Cloud, Python 3.12, NO secrets/API keys, so the public site can't make paid calls). Verified all 4 samples + custom page in light and dark: no errors, live buttons disabled. Deep links: `?strategy=lookahead|leaky|overfit|honest`.

## In progress
- Public live runs: Alissa adds keys + LIVE_RUNS_ENABLED=true in Streamlit secrets (decided Oct 6: disabled buttons made the demo look static)
- README

## Next
1. README (setup, how Nemotron/Token Factory/Sandboxes are used, model routing with measurements, disclaimer)
2. Demo video (< 3 min), submission by Oct 29
- Free Streamlit apps sleep when idle (~30s wake): open the site before/through judging (Dec 1–15)
- Ask Nebius whether auto card charging can be turned off / a spend cap set

## Decisions
- Track: Coding & Agentic Engineering
- Evidence is deterministic; LLM plans and explains
- Engine does not auto-shift positions (so real "forgot to shift" bugs are possible and catchable)
- Synthetic random-walk data for development (no real edge exists, so great-looking results = a bug)

## Known issues / open questions
- Signal-shift calendar detection covers weekday rules only (not day-of-month / month-of-year).
- Overfit strategy audit takes ~17s (point-in-time re-runs a 279-config grid search). Parallel sandbox forks could fix this.
- Honest strategy gets WARN on deflated Sharpe (not statistically significant) — correct on random data, but make sure the UI frames WARN as "not proven" rather than "broken."
- Planner retries: Super returns a broken-but-schema-valid plan (empty test_plan, or a finding garbled into another's snippet) ~1 in 3 runs on lookahead. plan_problems() catches these and retries (up to 3 attempts); after the fix, 8/8 lookahead plans flag L17/L18, 8/8 overfit flag L36, 8/8 honest clean. Cost: retried audits take ~6–10s longer; ~1 in 8 lookahead plans is still incomplete after 3 tries (audit continues; plan marked incomplete).
- Sandbox integrity limit: user code shares the CLI's process, so a deliberately hostile strategy could tamper with its own results (nonce markers stop casual forgery). The sandbox protects the host; a self-audit can only fool its author. Mention in README.
- Overfit audit in sandbox ~15s; parallel forks (stretch) could cut it.
- contree-sdk 0.3.6 API differs from online docs (no contree_client; uses ContreeConfig/IAMAuth). Trust the installed package over docs/reference/contree-sdk.md.
- Which real price dataset has a license that allows a public repo?
