"""Full audit of a built-in sample strategy:
static scan -> (Nano explains hits | Super plans | tests run, in parallel) -> Super explains.

    python -m scripts.audit_with_llm --strategy leaky
    python -m scripts.audit_with_llm --strategy all --seed 11
    python -m scripts.audit_with_llm --strategy leaky --sandbox   # tests run in a Token Factory Sandbox

Without --sandbox the tests run locally, which is OK ONLY for our own sample
strategies. User-submitted code must always go through agent.sandbox.
Writes outputs/<name>_audit.json.
"""
import argparse
import inspect
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent.interpreter import interpret
from agent.planner import plan_audit
from agent.sandbox import audit_in_sandbox
from agent.sanitize import strip_hints
from agent.scanner import explain_hits, static_scan
from attacks.evidence import report_to_evidence
from attacks.runner import run_audit
from engine.data import synthetic_prices
from strategies import STRATEGIES

OUT = Path("outputs")


def audit(name: str, seed: int, sandbox: bool = False) -> dict:
    mod = STRATEGIES[name]
    source = strip_hints(inspect.getsource(mod))
    prices = synthetic_prices(seed=seed)

    def timed(fn, *args, **kwargs):
        t = time.time()
        return fn(*args, **kwargs), time.time() - t

    def run_tests():
        if sandbox:
            return audit_in_sandbox(inspect.getsource(mod), prices)["evidence"]
        return report_to_evidence(run_audit(mod, prices))

    t0 = time.time()
    hits = static_scan(source)  # instant, deterministic; parses only
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_explain = pool.submit(timed, explain_hits, hits)
        f_plan = pool.submit(timed, plan_audit, source, getattr(mod, "DESCRIPTION", None),
                             scan_hits=[dict(h) for h in hits])
        f_tests = pool.submit(timed, run_tests)
        (hits, t_explain), (plan, t_plan), (evidence, t_tests) = f_explain.result(), f_plan.result(), f_tests.result()
    report, t_interp = timed(interpret, source, evidence, plan)
    total = time.time() - t0

    where = " [sandbox]" if sandbox else ""
    print(f"\n=== {name}  ->  {evidence['overall']}   (total {total:.1f}s | parallel: nano {t_explain:.1f}s, "
          f"plan {t_plan:.1f}s, tests{where} {t_tests:.1f}s | explain {t_interp:.1f}s)")
    for h in hits:
        print(f"  static L{h['line']} [{h['rule']}/{h['confidence']}] ({h['explained_by']}): {h['explanation']}")
    for r in plan["scan_review"]:
        print(f"  super review L{r['line']} {r['rule']}: {r['verdict']} - {r['reason']}")
    print("PLAN:", plan["strategy_summary"])
    for f in plan["findings"]:
        print(f"  suspicious L{f['line']} [{f['concern']}]: {f['snippet'].strip()}")
    print("REPORT:", report["headline"])
    for t in report["tests"]:
        print(f"  [{t['verdict']:>4}] {t['test']}: {t['explanation']}")
    for f in report["fixes"]:
        print(f"  fix L{f['line']}: {f['fix']}")
    if report["verdicts_overridden"]:
        print("  !! verdicts the LLM got wrong (overridden):", report["verdicts_overridden"])
    if report["unverified_numbers"]:
        print("  !! numbers not found in evidence:", report["unverified_numbers"])
    return {"strategy": name, "seed": seed, "sandbox": sandbox, "static_hits": hits, "plan": plan,
            "evidence": evidence, "report": report}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=list(STRATEGIES) + ["all"], default="all")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--sandbox", action="store_true", help="run the tests in a Token Factory Sandbox")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    names = list(STRATEGIES) if args.strategy == "all" else [args.strategy]
    for name in names:
        result = audit(name, args.seed, args.sandbox)
        (OUT / f"{name}_audit.json").write_text(json.dumps(result, indent=2))
    print(f"\nJSON saved to {OUT.resolve()}")


if __name__ == "__main__":
    main()
