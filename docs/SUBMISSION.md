# Devpost submission (ready to paste)

**Project name:** Backtest Auditor

**Tagline:** Is your backtest lying? An agent that catches lookahead, leakage and overfitting, then fixes the code and proves it.

**Track:** Coding and Agentic Engineering

**Demo URL:** https://backtest-auditor.streamlit.app
**Repo:** https://github.com/123Alissaa/backtest-auditor (MIT)
**Video:** _paste YouTube link_

---

## Description

### Inspiration
Trading backtests routinely look brilliant because of bugs, not skill: a signal that uses today's close to trade today, a `shift(-1)` that pulls in tomorrow's return, a z-score over the whole history, or the luckiest of hundreds of settings. These bugs are easy to write and nearly impossible to spot by reading code. Retail traders, finance students and quant interview candidates trust numbers like these every day.

### What it does
Backtest Auditor takes a trading strategy (Python) and:
1. **Scans** it with deterministic code rules for known leak patterns.
2. **Attacks** it with four deterministic tests (delay, hide-the-future, unseen data, deflated Sharpe), running the code **only inside a Nebius Token Factory Sandbox**.
3. **Explains** the evidence with **NVIDIA Nemotron**: the responsible line, why it leaks, and a suggested change.
4. **Fixes** it: Nemotron Super writes two candidate fixes, each re-tested in parallel in its own sandbox branch. A fix is accepted only if the tests pass and the strategy still trades.

The core rule: **the tests decide, the AI explains.** Nemotron's verdicts are overwritten with the test results, and every number it writes is checked against the evidence.

On the built-in gallery, a strategy claiming 50.6%/yr (Sharpe 3.43) is caught and fixed to an honest 1.0%/yr; a `shift(-1)` slip claiming 63.9%/yr is fixed to 4.9%/yr; a weekly back-fill bug that fools the delay test and every pattern rule is caught by hide-the-future. Two honest strategies pass, with no false alarms.

### How we built it
- **NVIDIA Nemotron Super** (`nemotron-3-super-120b-a12b`) on Token Factory plans the audit (flags lines, predicts each test's verdict, reviews rule hits), writes the report, and writes fixes.
- **NVIDIA Nemotron Nano** (`NVIDIA-Nemotron-3-Nano-30B-A3B`) writes cheap one-sentence explanations of rule hits, capped at 1,500 tokens with a fallback.
- **Nebius Token Factory Sandboxes:** a tagged base image (≈ 3 s per audit), hardened I/O (per-run output markers, timeouts), and **Git-like branching** so each candidate fix runs in its own branch of one snapshot, in parallel.
- All LLM calls use Token Factory's OpenAI-compatible API with strict JSON-schema output; guardrails verify cited lines, retry incomplete responses, and drop no-op fixes.
- Streamlit front end with a landing page, an 8-strategy gallery, and a live "audit your own code" page. A measured spend budget makes public live runs safe.

### Challenges we ran into
- **An LLM scanner wasn't reliable.** As a pattern checklist, Nemotron found the buggy line only ~1 in 3 runs, so we moved syntactic detection to code-parsing rules and gave Nano the explanation job.
- **Schema-valid isn't complete.** Super sometimes returned well-formed but empty plans; we added completeness checks and retries (8/8 afterwards on our measured samples).
- **Small leaks are hard to see.** A full-history z-score only flips some trades; checking 40 dates instead of 12 caught it on 4/4 random seeds with zero false alarms.
- **Our acceptance rule was too strict.** Requiring the delay test to PASS rejected a correct fix (it's noisy on random data); hide-the-future is now the decisive check.

### Accomplishments we're proud of
An agent that writes code, runs it in a sandbox, and accepts its own work only when deterministic tests agree. Every number on screen is reproducible.

### What we learned
Let models do the reading, reasoning and writing, and let code do the judging. And measure everything: several "obvious" design choices failed when we tested them.

### What's next
Real-market data with licensed sources, more bias checks (survivorship, transaction costs), and walk-forward re-optimization as an honest alternative for overfit strategies.

---

## Testing instructions (for judges)

No login needed. Open **https://backtest-auditor.streamlit.app** (if it shows "wake up", click it and wait ~30 s).

1. **Home:** the gallery shows 8 audited strategies; click any card to see its full audit, fix and evidence.
2. **Try it live:** click **✎ Audit your own code** → **Start from: Lookahead** → **Run audit** (~35 s). It fails, and the report highlights the line `signal = (c > sma)`.
3. Either add `.shift(1)` to the `return` line and re-run (it passes), or click **Fix it** (~35 s) to watch Nemotron write two fixes that the sandbox tests in parallel.
4. You can paste your own `run(prices)` strategy (the guide beside the editor explains the format) and upload your own price CSV.

Live audits are limited to 3 per browser session and a daily budget; saved audits are always available.

---

## Feedback on Nebius Token Factory, Sandboxes and NVIDIA models

What worked well: the OpenAI-compatible API made Nemotron a drop-in; strict JSON-schema output is reliable to parse; sandbox access arrived within a day; base-image tagging and branching made parallel fix-testing fast (3 branches in 2.6 s); sandbox results matched local runs to ~1e-13.

What would have helped (each verified while building; details and dates in FEEDBACK_NOTES.md in the repo):
1. **Model IDs:** the token-factory-cookbook lists `nvidia/nvidia-nemotron-3-nano-30b-a3b`, which returns "model does not exist"; the live ID is `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`. Case-insensitive IDs or a "did you mean" error would help.
2. **Reasoning fields differ by model:** Nano returns `reasoning`, Super returns `reasoning` and `reasoning_content`, and `content` starts with a stray newline. A per-model note in the model card would help.
3. **Nano with `reasoning_effort="none"`** puts the JSON answer in `reasoning` and leaves `content` empty (5/5 runs); with default reasoning it sometimes runs to 6,000+ tokens with no answer. A reasoning-token budget separate from `max_tokens` would make Nano usable for latency-sensitive calls.
4. **Strict schemas aren't fully enforced:** responses always parse, but ~1 in 3 Super plans had an empty required array. Supporting `minItems`, or documenting which JSON Schema keywords strict mode enforces, would help.
5. **Structured-output docs:** the Python example passes the schema directly as `json_schema` and is missing commas; the API needs `{"name", "schema", "strict"}` (422 otherwise).
6. **Contree SDK docs vs. PyPI:** the docs import `contree_client`, which `contree-sdk` 0.3.6 doesn't ship (it uses `ContreeConfig(IAMAuth(...))`); the SDK page uses a placeholder base URL; the project-ID variable has three names (`NEBIUS_PROJECT_ID`, `CONTREE_PROJECT`, `NEBIUS_AI_PROJECT`), and the docs don't say where to find it.
7. **Sandbox errors:** without access, the SDK raises a bare `ForbiddenError`, while the API says `403 Insufficient permissions: list`; `/v1/whoami` shows permissions but isn't mentioned in the docs.
8. **Undocumented sandbox behaviors we had to probe:** relative upload paths land in `/`, stdout is silently truncated at 64 KB, and a timed-out run returns `exit_code=-1` with the internal `timed_out` flag not exposed.
