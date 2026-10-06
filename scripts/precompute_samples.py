"""Run the full audit once per sample strategy and save it for the public demo.

    python -m scripts.precompute_samples            # all 4 samples
    python -m scripts.precompute_samples --strategy leaky

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
from agent.pipeline import run_full_audit, sample_source
from engine.data import synthetic_prices
from strategies import STRATEGIES

OUT = Path(__file__).resolve().parent.parent / "app" / "samples"
SEED = 7


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=list(STRATEGIES) + ["all"], default="all")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    names = list(STRATEGIES) if args.strategy == "all" else [args.strategy]
    for name in names:
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


if __name__ == "__main__":
    main()
