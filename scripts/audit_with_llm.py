"""Full audit of a built-in sample strategy from the terminal (same pipeline as the UI).

    python -m scripts.audit_with_llm --strategy leaky
    python -m scripts.audit_with_llm --strategy all --seed 11
    python -m scripts.audit_with_llm --strategy leaky --sandbox   # tests run in a Token Factory Sandbox

Without --sandbox the tests run locally, which is OK ONLY for our own sample
strategies. User-submitted code must always go through the sandbox.
Uses Token Factory credits (Nano + Super calls). Writes outputs/<name>_audit.json.
"""
import argparse
import json
from pathlib import Path

from agent.pipeline import AuditFailed, run_full_audit, sample_source
from engine.data import synthetic_prices
from strategies import STRATEGIES

OUT = Path("outputs")


def audit(name: str, seed: int, sandbox: bool = False) -> dict:
    mod = STRATEGIES[name]
    out = run_full_audit(sample_source(mod), synthetic_prices(seed=seed), sample_module=None if sandbox else mod)
    hits, plan, evidence, report, t = out["static_hits"], out["plan"], out["evidence"], out["report"], out["timings"]

    where = " [sandbox]" if sandbox else ""
    print(f"\n=== {name}  ->  {evidence['overall']}   (tests{where} {t['tests']:.1f}s | parallel: nano "
          f"{t['explain_hits']:.1f}s, plan {t['plan']:.1f}s | report {t['report']:.1f}s)")
    for h in hits:
        print(f"  static L{h['line']} [{h['rule']}/{h['confidence']}] ({h['explained_by']}): {h['explanation']}")
    for r in plan["scan_review"]:
        print(f"  super review L{r['line']} {r['rule']}: {r['verdict']} - {r['reason']}")
    print("PLAN:", plan["strategy_summary"], f"(attempts: {plan['attempts']})")
    if plan["incomplete"]:
        print("  !! plan still incomplete after retries:", plan["problems"])
    for f in plan["findings"]:
        print(f"  suspicious L{f['line']} [{f['concern']}]: {f['snippet'].strip()}")
    print("REPORT:", report["headline"])
    for r in report["tests"]:
        print(f"  [{r['verdict']:>4}] {r['test']}: {r['explanation']}")
    for f in report["fixes"]:
        print(f"  fix L{f['line']}: {f['fix']}")
    if report["verdicts_overridden"]:
        print("  !! verdicts the LLM got wrong (overridden):", report["verdicts_overridden"])
    if report["unverified_numbers"]:
        print("  !! numbers not found in evidence:", report["unverified_numbers"])
    return {"strategy": name, "seed": seed, **out}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=list(STRATEGIES) + ["all"], default="all")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--sandbox", action="store_true", help="run the tests in a Token Factory Sandbox")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    names = list(STRATEGIES) if args.strategy == "all" else [args.strategy]
    for name in names:
        try:
            result = audit(name, args.seed, args.sandbox)
        except AuditFailed as e:
            print(f"\n=== {name}: could not audit ({e.stage}): {e}")
            continue
        (OUT / f"{name}_audit.json").write_text(json.dumps(result, indent=2))
    print(f"\nJSON saved to {OUT.resolve()}")


if __name__ == "__main__":
    main()
