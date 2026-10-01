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

## Principles
- Numbers come only from deterministic tests (attacks/). The LLM may not invent or alter metrics.
- Untrusted code never runs on the host.
- Model IDs/URLs only via agent/config.py.

## Model routing (fill in with real IDs + reasoning once tested)
| Step | Model | Why |
|---|---|---|
| Plan | Super/Ultra | multi-step reasoning about code |
| Scan | Nano | cheap, fast, high volume |
| Explain | Super/Ultra | careful judgment on evidence |
