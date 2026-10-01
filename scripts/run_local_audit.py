"""Audit the built-in sample strategies locally and save comparison charts.

    python -m scripts.run_local_audit                 # all strategies
    python -m scripts.run_local_audit --strategy lookahead --seed 11

LOCAL ONLY FOR OUR OWN SAMPLE STRATEGIES. User-submitted code must run inside
Token Factory Sandboxes, never on the host (hackathon + safety requirement).
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from attacks.runner import run_audit
from engine.data import synthetic_prices
from strategies import STRATEGIES

OUT = Path("outputs")


def plot_shift(report, path: Path):
    shift = next(r for r in report.results if r.name == "signal_shift")
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(shift.curves["original"], label=f"Reported (Sharpe {shift.metrics['sharpe_original']:.2f})")
    ax.plot(shift.curves["shifted"], label=f"Signal delayed 1 bar (Sharpe {shift.metrics['sharpe_shifted']:.2f})")
    ax.set_yscale("log"); ax.set_title(f"{report.strategy}: reported vs. delayed signal")
    ax.set_ylabel("Equity (log scale)"); ax.legend(); fig.tight_layout()
    fig.savefig(path, dpi=130); plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", choices=list(STRATEGIES) + ["all"], default="all")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()
    prices = synthetic_prices(seed=args.seed)
    OUT.mkdir(exist_ok=True)
    names = list(STRATEGIES) if args.strategy == "all" else [args.strategy]
    for name in names:
        rep = run_audit(STRATEGIES[name], prices)
        m = rep.reported_metrics
        print(f"\n=== {name}  ->  {rep.overall} ===")
        print(f"Reported: CAGR {m['cagr']:.1%} | Sharpe {m['sharpe']:.2f} | Max DD {m['max_drawdown']:.1%}")
        for r in rep.results:
            print(f"  [{r.verdict:>4}] {r.name}: {r.summary}")
        plot_shift(rep, OUT / f"{name}_signal_shift.png")
    print(f"\nCharts saved to {OUT.resolve()}")


if __name__ == "__main__":
    main()
