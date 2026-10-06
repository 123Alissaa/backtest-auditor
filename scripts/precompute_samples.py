"""Run the full audit once per sample strategy and save it for the public demo.

    python -m scripts.precompute_samples            # all 4 samples
    python -m scripts.precompute_samples --strategy leaky
    python -m scripts.precompute_samples --fix-only     # add saved "Fix it" results to existing audits

USES TOKEN FACTORY CREDITS (about one audit per sample) and sandbox runs.
Tests run in a Token Factory Sandbox, exactly like a live audit. The demo then
shows these saved results instantly, with no paid calls.
Writes app/samples/<name>.json (committed to the repo).
"""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from agent.config import settings
from agent.fixer import eligibility, fix_strategy
from agent.pipeline import run_full_audit, sample_source
from engine.data import synthetic_prices
from strategies import STRATEGIES

OUT = Path(__file__).resolve().parent.parent / "app" / "samples"
SEED = 7


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=list(STRATEGIES) + ["all"], default="all")
    ap.add_argument("--fix-only", action="store_true", help="only add fix results to existing saved audits")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    names = list(STRATEGIES) if args.strategy == "all" else [args.strategy]
    for name in names:
        if args.fix_only:
            add_fix(name)
            continue
        mod = STRATEGIES[name]
        result = run_full_audit(sample_source(mod), synthetic_prices(seed=SEED))  # sandbox, like a live run
        result.update({
            "strategy": name, "seed": SEED, "description": getattr(mod, "DESCRIPTION", ""),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "models": {"fast": settings.model_fast, "reasoning": settings.model_reasoning},
        })
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(result, indent=1))
        plan = result["plan"]
        print(f"{name:10s} {result['evidence']['overall']:4s} | plan attempts {plan['attempts']}"
              f"{' INCOMPLETE' if plan['incomplete'] else ''} | {path.stat().st_size // 1024} KB")


def add_fix(name: str):
    path = OUT / f"{name}.json"
    result = json.loads(path.read_text())
    if not eligibility(result["evidence"], result["plan"])[0]:
        print(f"{name:10s} not fixable in code (UI explains why)")
        return
    fix = fix_strategy(result["source"], result["evidence"], result["plan"], synthetic_prices(seed=result["seed"]))
    for i, a in enumerate(fix["attempts"]):
        if i != fix["accepted"]:
            a["curves"] = None  # only the accepted fix is charted; keeps the file small
    result["fix"] = fix
    path.write_text(json.dumps(result, indent=1))
    status = "accepted" if fix["accepted"] is not None else "NO FIX PASSED"
    print(f"{name:10s} fix {status} after {len(fix['attempts'])} candidate(s) | {path.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
