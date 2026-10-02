# Progress

_Last updated: Oct 2, 2026_

## Done
- Repo scaffold, CLAUDE.md, requirements checklist, MIT license
- Backtest engine (t → t+1 timing convention) + metrics (CAGR, Sharpe, max drawdown)
- 4 sample strategies on synthetic data: honest, lookahead (~50% CAGR, fake), leaky (centered window), overfit (best of 279 configs)
- Attacks: signal shift, point-in-time, walk-forward, deflated Sharpe ratio
- pytest suite (11 tests): every broken strategy caught by the right test, honest never FAILs, across multiple seeds
- scripts/run_local_audit.py with reported-vs-delayed equity chart
- Official docs saved to docs/reference/ (local only)
- Token Factory working: Nano + Super model IDs verified live; `python -m scripts.hello_nemotron` works; reasoning fields confirmed in agent/llm.py
- venv rebuilt on Python 3.12

## In progress
- Nemotron planner + interpreter: working end to end on all 4 samples (`python -m scripts.audit_with_llm`). Planner flags the right line on lookahead (L18), leaky (L19), overfit (L36) and nothing on honest.
- Sandboxes beta access granted 2026-10-02. agent/sandbox.py runs all attacks inside a Token Factory Sandbox (`--sandbox` flag): ~3s per audit (~15s overfit); evidence matches local runs (floats within 1e-9). Crashes, missing run(), syntax errors, SystemExit, timeouts and forged output all handled.

## Next
1. Nano scan step (hard requirement: Nano for fast/cheap calls; currently only Super is used)
2. Signal-shift calendar fix (see known issues)
3. Report UI + charts (sandbox returns signal-shift curves for the chart)

## Decisions
- Track: Coding & Agentic Engineering
- Evidence is deterministic; LLM plans and explains
- Engine does not auto-shift positions (so real "forgot to shift" bugs are possible and catchable)
- Synthetic random-walk data for development (no real edge exists, so great-looking results = a bug)

## Known issues / open questions
- Signal-shift test can WARN/FAIL on calendar-dependent strategies (e.g. weekday filters) for reasons other than lookahead; the interpreter should consider this.
- Overfit strategy audit takes ~17s (point-in-time re-runs a 279-config grid search). Parallel sandbox forks could fix this.
- Honest strategy gets WARN on deflated Sharpe (not statistically significant) — correct on random data, but make sure the UI frames WARN as "not proven" rather than "broken."
- Sandbox integrity limit: user code shares the CLI's process, so a deliberately hostile strategy could tamper with its own results (nonce markers stop casual forgery). The sandbox protects the host; a self-audit can only fool its author. Mention in README.
- Overfit audit in sandbox ~15s; parallel forks (stretch) could cut it.
- contree-sdk 0.3.6 API differs from online docs (no contree_client; uses ContreeConfig/IAMAuth). Trust the installed package over docs/reference/contree-sdk.md.
- Interpreter still explains overfit's signal_shift FAIL as lookahead (it's the weekday filter, see signal-shift issue above). Better fix is in the test: skip/annotate signal_shift when positions depend on calendar.
- Which real price dataset has a license that allows a public repo?
