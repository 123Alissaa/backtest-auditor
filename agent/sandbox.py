"""Token Factory Sandboxes integration -- NOT IMPLEMENTED YET.

Intended contract (implement with the Contree SDK once credits arrive, working
from the official docs saved in docs/reference/ -- do not guess method names):

    run_in_sandbox(files: dict[str, str], command: str, timeout_s: int = 120) -> SandboxResult

    - Upload the strategy file + price data + our attack runner into a fresh sandbox
    - Run the command, e.g. `python -m attacks.cli --strategy user_strategy.py`
    - Return stdout, stderr, exit code, and any artifact files (JSON results, charts)

Later (stretch): set up once, checkpoint, then fork one sandbox per attack test
and run them in parallel -- Sandboxes support Git-like branching from checkpoints.
"""
from dataclasses import dataclass, field


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    artifacts: dict[str, bytes] = field(default_factory=dict)


def run_in_sandbox(files: dict[str, str], command: str, timeout_s: int = 120) -> SandboxResult:
    raise NotImplementedError("Implement with the Contree SDK -- see docstring and docs/reference/.")
