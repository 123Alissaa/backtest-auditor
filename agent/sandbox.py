"""Token Factory Sandboxes integration (Contree SDK).

User-submitted strategy code runs ONLY here, never on the host.

How an audit runs:
1. ensure_base_image(): python:3.12-slim + pinned pandas/numpy, built once and
   saved under BASE_TAG so later audits skip the ~11s pip install.
2. audit_in_sandbox(): uploads our engine/ + attacks/ code, the user's strategy
   and the prices (CSV) into /work, runs `python -m attacks.cli`, and parses the
   JSON it prints. Nothing secret is uploaded: no .env, no API keys.

Notes from testing contree-sdk 0.3.6 (it differs from the online docs):
- Client: ContreeSync(ContreeConfig(auth=IAMAuth(token, project_id, base_url))).
- Relative upload paths land in "/", so we use absolute /work/... paths.
- stdout is truncated at 64 KB unless truncate_output_at is raised.
- images.use(tag, strict=True) raises NotFoundError for a missing tag.
- The sandbox has internet access (pip works).
- A run that hits its timeout comes back with exit_code -1 and empty output.
- No host environment variables reach the sandbox (only the image's own, e.g. GPG_KEY).
"""
import json
import secrets
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
from contree_sdk import ContreeSync
from contree_sdk.auth import IAMAuth
from contree_sdk.config import ContreeConfig
from contree_sdk.sdk.exceptions.api import NotFoundError

from agent.config import settings
from attacks.cli import markers

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ("engine", "attacks")              # our code the strategy is audited with
PINNED = ("pandas==3.0.6", "numpy==2.5.3")    # must match requirements.txt so results match local runs
BASE_IMAGE = "python:3.12-slim"
BASE_TAG = "backtest-auditor:base-pd3.0.6-np2.5.3"
WORKDIR = "/work"
MAX_OUTPUT_BYTES = 4 * 1024 * 1024


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    artifacts: dict[str, bytes] = field(default_factory=dict)


class SandboxAuditError(RuntimeError):
    """The audit couldn't produce evidence (user code crashed, broke the contract, timed out...)."""

    def __init__(self, message: str, stage: str = "sandbox", details: str = ""):
        super().__init__(message)
        self.stage = stage
        self.details = details


_client: ContreeSync | None = None


def get_client() -> ContreeSync:
    global _client
    if _client is None:
        if not settings.api_key or not settings.project_id:
            raise RuntimeError("Set NEBIUS_API_KEY and NEBIUS_PROJECT_ID in .env to use Sandboxes.")
        auth = IAMAuth(token=settings.api_key, project_id=settings.project_id, base_url=settings.contree_url)
        _client = ContreeSync(ContreeConfig(auth=auth))
    return _client


def ensure_base_image():
    """Return the prepared base image, building and tagging it on first use."""
    sdk = get_client()
    try:
        return sdk.images.use(BASE_TAG, strict=True)
    except NotFoundError:
        pass
    pip = "pip install -q --disable-pip-version-check --root-user-action=ignore " + " ".join(PINNED)
    built = sdk.images.use(BASE_IMAGE).run(shell=pip, tag=BASE_TAG, disposable=False, timeout=600).wait()
    if built.exit_code != 0:
        raise SandboxAuditError("Building the sandbox base image failed.", "setup", built.stderr or "")
    return sdk.images.use(BASE_TAG, strict=True)


def _our_code() -> dict[str, bytes]:
    files = {}
    for pkg in PACKAGES:
        for path in (ROOT / pkg).glob("*.py"):
            files[f"{WORKDIR}/{pkg}/{path.name}"] = path.read_bytes()
    return files


def run_in_sandbox(files: dict[str, bytes], command: list[str], timeout_s: int = 120,
                   env: dict[str, str] | None = None) -> SandboxResult:
    """Upload `files` (absolute sandbox path -> content) and run `command` in WORKDIR on the base image."""
    image = ensure_base_image()
    result = image.run(
        command=command[0], args=command[1:], cwd=WORKDIR, files=files, env=env,
        timeout=timeout_s, truncate_output_at=MAX_OUTPUT_BYTES,
    ).wait()
    return SandboxResult(stdout=result.stdout or "", stderr=result.stderr or "", exit_code=result.exit_code)


def parse_cli_output(res: SandboxResult, nonce: str, timeout_s: int) -> dict:
    begin, end = markers(nonce)
    if res.exit_code == -1 and begin not in res.stdout:
        raise SandboxAuditError(f"The strategy didn't finish within the {timeout_s}s time limit.", "timeout")
    if begin not in res.stdout:
        raise SandboxAuditError("The audit produced no result.", "sandbox", (res.stderr or res.stdout)[-2000:])
    if end not in res.stdout:
        raise SandboxAuditError("The audit output was cut off (too large).", "sandbox")
    return json.loads(res.stdout.split(begin, 1)[1].split(end, 1)[0])


def prepare_workspace(prices: pd.DataFrame):
    """Snapshot = base image + our engine/attacks code + prices in /work (Contree branching).

    Every strategy variant then runs in its own branch of this snapshot, in parallel,
    without re-uploading anything but the strategy file. ~3s, once per fix session."""
    files = _our_code()
    files[f"{WORKDIR}/prices.csv"] = prices.to_csv(float_format="%.17g").encode()  # %.17g: exact float round-trip
    ws = ensure_base_image().run(shell="true", files=files, cwd=WORKDIR, disposable=False).wait()
    if ws.exit_code != 0 or not ws.uuid:
        raise SandboxAuditError("Preparing the sandbox workspace failed.", "setup", ws.stderr or "")
    return ws


def audit_variant(workspace, strategy_source: str, timeout_s: int = 300) -> dict:
    """Run all attacks on one strategy variant in a fresh branch of `workspace`."""
    nonce = secrets.token_hex(16)
    r = workspace.run(command="python", args=["-m", "attacks.cli", "--strategy", "user_strategy.py",
                                              "--prices", "prices.csv"],
                      files={f"{WORKDIR}/user_strategy.py": strategy_source.encode()}, cwd=WORKDIR,
                      env={"AUDIT_NONCE": nonce}, timeout=timeout_s, truncate_output_at=MAX_OUTPUT_BYTES).wait()
    out = parse_cli_output(SandboxResult(r.stdout or "", r.stderr or "", r.exit_code), nonce, timeout_s)
    if not out.get("ok"):
        raise SandboxAuditError(out.get("error", "Unknown error"), out.get("stage", "audit"), out.get("traceback", ""))
    return {"evidence": out["evidence"], "curves": out["curves"]}


def audit_in_sandbox(strategy_source: str, prices: pd.DataFrame, timeout_s: int = 300) -> dict:
    """Run all attacks on untrusted strategy code inside a sandbox.

    Returns {"evidence": <attacks.evidence format>, "curves": {...}}.
    Raises SandboxAuditError if the strategy can't be audited.
    """
    files = _our_code()
    files[f"{WORKDIR}/user_strategy.py"] = strategy_source.encode()
    files[f"{WORKDIR}/prices.csv"] = prices.to_csv(float_format="%.17g").encode()  # %.17g: exact float round-trip

    nonce = secrets.token_hex(16)
    res = run_in_sandbox(files, ["python", "-m", "attacks.cli", "--strategy", "user_strategy.py",
                                 "--prices", "prices.csv"], timeout_s, env={"AUDIT_NONCE": nonce})
    out = parse_cli_output(res, nonce, timeout_s)
    if not out.get("ok"):
        raise SandboxAuditError(out.get("error", "Unknown error"), out.get("stage", "audit"), out.get("traceback", ""))
    return {"evidence": out["evidence"], "curves": out["curves"]}
