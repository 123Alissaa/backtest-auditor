# Progress

_Last updated: Sep 27, 2026_

## Done
- Repo scaffold, CLAUDE.md, requirements checklist, MIT license
- Backtest engine (t → t+1 timing convention) + metrics (CAGR, Sharpe, max drawdown)
- 4 sample strategies on synthetic data: honest, lookahead (~50% CAGR, fake), leaky (centered window), overfit (best of 279 configs)
- Attacks: signal shift, point-in-time, walk-forward, deflated Sharpe ratio
- pytest suite (11 tests): every broken strategy caught by the right test, honest never FAILs, across multiple seeds
- scripts/run_local_audit.py with reported-vs-delayed equity chart

## In progress
- Waiting on Token Factory credits

## Next
1. Save official docs into docs/reference/ (see its README)
2. Fill .env; run `python -m scripts.hello_nemotron`; fix reasoning-field handling in agent/llm.py
3. Sandbox hello world with the Contree SDK
4. Implement agent/sandbox.py: run a strategy + attacks inside a sandbox, return JSON results
5. Nemotron planner + interpreter

## Decisions
- Track: Coding & Agentic Engineering
- Evidence is deterministic; LLM plans and explains
- Engine does not auto-shift positions (so real "forgot to shift" bugs are possible and catchable)
- Synthetic random-walk data for development (no real edge exists, so great-looking results = a bug)

## Known issues / open questions
- Signal-shift test can WARN/FAIL on calendar-dependent strategies (e.g. weekday filters) for reasons other than lookahead; the interpreter should consider this.
- Overfit strategy audit takes ~17s (point-in-time re-runs a 279-config grid search). Parallel sandbox forks could fix this.
- Honest strategy gets WARN on deflated Sharpe (not statistically significant) — correct on random data, but make sure the UI frames WARN as "not proven" rather than "broken."
- Which real price dataset has a license that allows a public repo?
