# Architecture (target)

```
User (web UI)
  │  strategy.py + price data
  ▼
Orchestrator (agent/)
  ├─ 1. PLAN      Nemotron Super/Ultra reads the code → which tests, what params,
  │               suspicious lines, declared number of trials
  ├─ 2. EXECUTE   Token Factory Sandbox: install deps, run strategy + attacks/
  │               (stretch: checkpoint once, fork one sandbox per test in parallel)
  ├─ 3. SCAN      Nemotron Nano: fast pass over code for known leak patterns
  │               (centered windows, full-sample fits, missing shifts)
  └─ 4. EXPLAIN   Nemotron Super/Ultra: evidence JSON → plain-English verdicts,
                  points at exact code lines, never invents numbers
  ▼
Report: per-test verdict + evidence + reported vs honest equity curve
```

## Fix loop (agent/fixer.py)
- `prepare_workspace()` snapshots base image + engine/attacks + prices once; `audit_variant()` runs each candidate fix in its own branch of that snapshot (parallel threads). This is Contree's Git-like branching.
- Super writes 2 candidates per round (max 2 rounds); deterministic pre-checks run first; acceptance is decided only by sandbox evidence (+ still trading). Overfitting is out of scope by design.

## Sandbox execution (agent/sandbox.py)
- Base image `backtest-auditor:base-pd3.0.6-np2.5.3`: `python:3.12-slim` + pinned pandas/numpy, built once (~14s) and reused (~0.3s lookup).
- Each audit uploads `engine/*.py`, `attacks/*.py`, `user_strategy.py` and `prices.csv` to `/work`, runs `python -m attacks.cli`, and parses JSON between per-run nonce markers. ~3s per audit.
- Nothing secret is uploaded; no host env vars reach the sandbox. The sandbox has internet access.
- Failures come back as `SandboxAuditError(stage=load|contract|audit|timeout|sandbox)` with the traceback tail.
- Stretch: checkpoint the prepared sandbox and fork one per attack in parallel.

## Deterministic tests: notes
- point_in_time checks 40 dates (12 when the strategy declares PARAM_GRID, since each check re-runs the search). Depends only on the code, so results are reproducible.
- signal_shift delays positions one bar; if positions are calendar-dependent (some weekdays >10% exposure, others <2%), it delays to the same weekday one week later instead, so weekday rules aren't mistaken for lookahead. Evidence records `calendar_dependent`, `delay`, `weekday_exposure`.

## Principles
- Numbers come only from deterministic tests (attacks/). The LLM may not invent or alter metrics.
- Untrusted code never runs on the host.
- Model IDs/URLs only via agent/config.py.

## Model routing
| Step | Model | Code | Why |
|---|---|---|---|
| Plan | `nvidia/nemotron-3-super-120b-a12b` | agent/planner.py | multi-step reasoning about code; ~5–10s |
| Scan | rules + `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | agent/scanner.py | rules (ast) find syntactic leak patterns instantly; Nano writes one sentence per hit (~2–3s, capped at 1500 tokens, falls back to rule text) |
| Explain | `nvidia/nemotron-3-super-120b-a12b` | agent/interpreter.py | careful judgment on evidence; ~3–13s |

Why Scan isn't an LLM checklist: tested 2026-10-02, a Nano (and Super) checklist scan found the lookahead/overfit lines only ~1 in 3 runs, took 3–54s, and Nano sometimes reasoned past 6000 tokens with no answer. Syntactic patterns (centered windows, negative shifts, bfill, full-sample stats/fits, i+1 indexing) are found by parsing the code; semantic bugs stay with the Super planner, which also reviews every rule hit (`scan_review`: confirmed/dismissed).

Flow per audit: static scan (instant) → in parallel {Nano explains hits, Super plans, sandbox tests} → Super explains. ~10–28s total.

All LLM steps use JSON-schema structured output via `agent.llm.chat_json` (handles Nano's empty-content quirk, retries bad JSON) (`response_format={"type": "json_schema", "json_schema": {"name", "schema", "strict"}}`).

## LLM guardrails (agent/)
- **Rules can't hallucinate:** static hits come from parsing, and the snippet is the exact source line. Nano only restates the rule's fact for that line; it's told never to call code safe (judging is Super's job).
- **No answer leaks:** `sanitize.strip_hints` blanks comments, docstrings, `PLANTED_BUG` and `NAME` before code reaches the model, keeping line numbers intact.
- **Cited lines are real:** `planner.verify_findings` checks each snippet is on its cited line (relocating or rejecting otherwise).
- **Verdicts are deterministic:** the interpreter's verdicts are overwritten with the test results; disagreements are logged in `verdicts_overridden`.
- **Numbers are checked:** every decimal/percentage in the explanation is matched against evidence metrics; misses go to `unverified_numbers`.
- **Evidence contract:** `attacks/evidence.report_to_evidence` → plain JSON. The sandbox runner must return this exact shape.
