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

## Model routing
| Step | Model | Code | Why |
|---|---|---|---|
| Plan | `nvidia/nemotron-3-super-120b-a12b` | agent/planner.py | multi-step reasoning about code; ~5–10s |
| Scan | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | not built yet | cheap, fast, high volume |
| Explain | `nvidia/nemotron-3-super-120b-a12b` | agent/interpreter.py | careful judgment on evidence; ~3–13s |

Both LLM steps use JSON-schema structured output (`response_format={"type": "json_schema", "json_schema": {"name", "schema", "strict"}}`).

## LLM guardrails (agent/)
- **No answer leaks:** `sanitize.strip_hints` blanks comments, docstrings, `PLANTED_BUG` and `NAME` before code reaches the model, keeping line numbers intact.
- **Cited lines are real:** `planner.verify_findings` checks each snippet is on its cited line (relocating or rejecting otherwise).
- **Verdicts are deterministic:** the interpreter's verdicts are overwritten with the test results; disagreements are logged in `verdicts_overridden`.
- **Numbers are checked:** every decimal/percentage in the explanation is matched against evidence metrics; misses go to `unverified_numbers`.
- **Evidence contract:** `evidence.report_to_evidence` → plain JSON. The sandbox runner must return this exact shape.
