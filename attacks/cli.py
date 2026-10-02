"""Run every attack on one strategy file and print the results as JSON.

This is what runs INSIDE the Token Factory Sandbox (agent/sandbox.py uploads
it with engine/ and attacks/). It loads untrusted strategy code, so never run
it on the host for user-submitted code.

    python -m attacks.cli --strategy user_strategy.py --prices prices.csv

Prints one JSON object between BEGIN/END markers:
    {"ok": true, "evidence": {...}, "curves": {"dates": [...], "original": [...], "shifted": [...]}}
    {"ok": false, "error": "...", "stage": "load" | "contract" | "audit"}

The markers include a per-run nonce from $AUDIT_NONCE, removed from the
environment before the strategy loads, so strategy code can't casually print
a fake result. (It shares our process, so a deliberately hostile strategy
could still tamper; the sandbox protects the host, not a self-audit's honesty.)
"""
import argparse
import importlib.util
import json
import os
import sys
import traceback

import pandas as pd



def markers(nonce: str) -> tuple[str, str]:
    return f"=====AUDIT-JSON-BEGIN-{nonce}=====", f"=====AUDIT-JSON-END-{nonce}====="


def load_strategy(path: str):
    spec = importlib.util.spec_from_file_location("user_strategy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_contract(module) -> str | None:
    """Return an error message if the strategy doesn't follow the expected interface."""
    if not callable(getattr(module, "run", None)):
        return "The strategy must define a function run(prices) that returns a pandas Series of positions."
    grid = getattr(module, "PARAM_GRID", None)
    if grid is not None and not callable(getattr(module, "positions_for", None)):
        return "PARAM_GRID is set, so the strategy must also define positions_for(prices, **params)."
    if not hasattr(module, "NAME"):
        module.NAME = "user_strategy"
    return None


def load_prices(path: str) -> pd.DataFrame:
    prices = pd.read_csv(path, index_col=0, parse_dates=True)
    if "close" not in prices.columns:
        raise ValueError("prices.csv must have a 'close' column")
    return prices


def _emit(payload: dict, nonce: str) -> None:
    begin, end = markers(nonce)
    sys.stdout.write(f"\n{begin}\n{json.dumps(payload)}\n{end}\n")
    sys.stdout.flush()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--strategy", required=True)
    ap.add_argument("--prices", required=True)
    args = ap.parse_args(argv)
    nonce = os.environ.pop("AUDIT_NONCE", "local")

    stage = "load"
    try:
        module = load_strategy(args.strategy)
        prices = load_prices(args.prices)
        stage = "contract"
        problem = check_contract(module)
        if problem:
            _emit({"ok": False, "stage": stage, "error": problem}, nonce)
            return 2
        stage = "audit"
        from attacks.evidence import report_to_evidence
        from attacks.runner import run_audit

        report = run_audit(module, prices)
        shift = next(r for r in report.results if r.name == "signal_shift")
        curves = {
            "dates": [str(d.date()) for d in shift.curves["original"].index],
            "original": [round(float(x), 6) for x in shift.curves["original"]],  # chart only; keeps output small
            "shifted": [round(float(x), 6) for x in shift.curves["shifted"]],
        }
        _emit({"ok": True, "evidence": report_to_evidence(report), "curves": curves}, nonce)
        return 0
    except (Exception, SystemExit) as exc:  # report user-code failures as data; SystemExit isn't an Exception
        tb = traceback.format_exc(limit=-3)
        _emit({"ok": False, "stage": stage, "error": f"{type(exc).__name__}: {exc}", "traceback": tb}, nonce)
        return 1


if __name__ == "__main__":
    sys.exit(main())
