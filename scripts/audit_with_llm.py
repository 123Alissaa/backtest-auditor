"""Full audit of a built-in sample strategy: Nemotron plan -> deterministic tests -> Nemotron explanation.

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
from pathlib import Path

from agent.interpreter import interpret
from agent.planner import plan_audit
from agent.sandbox import audit_in_sandbox
from agent.sanitize import strip_hints
from attacks.evidence import report_to_evidence
from attacks.runner import run_audit
from engine.data import synthetic_prices
from strategies import STRATEGIES

OUT = Path("outputs")


def audit(name: str, seed: int, sandbox: bool = False) -> dict:
    mod = STRATEGIES[name]
    source = strip_hints(inspect.getsource(mod))
    prices = synthetic_prices(seed=seed)

    t0 = time.time()
    plan = plan_audit(source, getattr(mod, "DESCRIPTION", None))
    t1 = time.time()
    if sandbox:
        evidence = audit_in_sandbox(inspect.getsource(mod), prices)["evidence"]
    else:
        evidence = report_to_evidence(run_audit(mod, prices))
    t2 = time.time()
    report = interpret(source, evidence, plan)
    t3 = time.time()

    print(f"\n=== {name}  ->  {evidence['overall']}   (plan {t1 - t0:.1f}s | tests{' [sandbox]' if sandbox else ''} {t2 - t1:.1f}s | explain {t3 - t2:.1f}s)")
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
    return {"strategy": name, "seed": seed, "sandbox": sandbox, "plan": plan, "evidence": evidence, "report": report}


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
