# Backtest Auditor — Nebius x NVIDIA Global AI Hackathon

## Who I am
I'm Alissa, a senior CS student. Comfortable with Python and backend work (APIs, pipelines, PostgreSQL). New to Nebius Token Factory, Token Factory Sandboxes, NVIDIA Nemotron, and quant backtesting. Building solo. Be casual and direct.

## Start of every session
Read PROGRESS.md first. Then confirm today's goal with me before writing code.

## What we're building
An AI agent that audits trading-strategy backtests for the three most common ways they lie: lookahead bias, data leakage, overfitting.
Flow: user submits strategy code + price data → Nemotron reads the code and writes an audit plan → strategy runs inside a Token Factory Sandbox → deterministic attack tests run → Nemotron interprets the evidence → report with a verdict per test, evidence (code line + before/after metrics), and reported vs. honest equity curve.

Core principle: evidence comes from deterministic, reproducible tests, not LLM opinion. The LLM plans, reads code, and explains; the numbers come from code we run.

Demo "wow" moment: the lookahead sample shows ~50% CAGR / Sharpe ~3.4; after the one-bar signal shift its equity curve collapses to flat, side by side. Second beat: the leaky strategy PASSES the shift test but the point-in-time test still catches it.

## Hard requirements (never violate — flag before breaking any)
Track: Coding & Agentic Engineering.
- All inference via Nebius Token Factory using NVIDIA Nemotron. Nano-class for fast/cheap calls, Super/Ultra for planning and judgment. Routing is deliberate and documented in the README.
- User-submitted code runs ONLY inside Token Factory Sandboxes, never on the host. (scripts/run_local_audit.py is only for our own sample strategies.)
- Public GitHub repo, MIT license visible at top.
- README: setup/run instructions + how Nemotron, Token Factory, Sandboxes (and any other Nebius tools / Tavily) are used.
- Working hosted demo URL with preloaded sample strategies.
- Public YouTube demo video ≤ 3 minutes, audio explains Token Factory + Nemotron usage.
- Feedback on Nebius/NVIDIA tools collected in FEEDBACK_NOTES.md.
- Only publicly shareable data in the repo. docs/reference/ is gitignored for third-party docs.
- App + README say "educational tool, not financial advice."
- Deadline Oct 30, 2026, 10:00 AM PT. Target submission Oct 29.
Judging: Technological Implementation, Design (complete product, not a PoC), Potential Impact (retail traders, finance students, quant interview candidates), Quality of the Idea.
Full checklist: docs/REQUIREMENTS.md.

## Repo map
- engine/ — data (synthetic GBM prices), backtest loop, metrics
- strategies/ — 4 samples: honest, lookahead, leaky, overfit (PLANTED_BUG is test ground truth; the auditor must never read it)
- attacks/ — signal_shift, point_in_time, walk_forward, deflated_sharpe, runner
- agent/ — config (.env), llm (Token Factory chat wrapper), sandbox (stub, not implemented)
- scripts/ — run_local_audit (samples only), hello_nemotron
- app/ — UI (not started)
- docs/ — REQUIREMENTS.md, ARCHITECTURE.md, reference/ (local-only official docs)

## Commands
- Tests: `pytest -q` (all, ~35s) or `pytest -q -m "not slow"` (fast)
- Local audit: `python -m scripts.run_local_audit [--strategy lookahead] [--seed 7]` → charts in outputs/
- First Nemotron call: `python -m scripts.hello_nemotron`

## Timing convention (critical)
positions[t] = exposure held from close[t-1] to close[t]; it may only use data through close[t-1]. The engine does NOT shift for the strategy. Our own code must never contain lookahead — call out any off-by-one in shifting/indexing.

## MVP scope, in order
1. ✅ Local engine + metrics
2. ✅ Sample strategies (lookahead, leakage, overfit, honest)
3. ✅ Deterministic attacks + pytest
4. Sandbox execution (agent/sandbox.py)
5. Nemotron planner (reads code → plan) + interpreter (evidence → plain-English report)
6. Report UI + charts
7. Deploy, README, video, submission
Stretch only after 1–7: Tavily, parameter-perturbation test, more bias checks, parallel sandbox forks from a checkpoint.
Push back if I try to add scope before the current step works.

## How to work with me
- For Token Factory, Sandboxes, the Contree SDK, or Nemotron model IDs/params: check docs/reference/ first. If not covered, say you're unsure and tell me what to look up. Never invent API methods, params, or model names.
- Nemotron models are reasoning models; see agent/llm.py for handling empty content / separate reasoning field.
- Run `pytest` after changes to engine/, strategies/, or attacks/.
- Explain new finance or platform concepts briefly in plain language the first time.
- Keep secrets in .env. Model IDs and URLs only via agent/config.py.
- When something about Nebius/NVIDIA tooling is confusing or broken, add a line to FEEDBACK_NOTES.md.
