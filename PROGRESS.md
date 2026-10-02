# Progress

_Last updated: Oct 2, 2026_

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
- Tests: 59 offline + 7 opt-in (`RUN_SANDBOX_TESTS=1 pytest -m sandbox`, `RUN_LLM_TESTS=1 pytest -m llm`)

## In progress
- Nothing — next up is the report UI

## Next
1. Report UI + charts (sandbox returns signal-shift curves for the chart)
2. Hosted demo URL, README, video, submission

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
