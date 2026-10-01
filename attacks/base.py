from dataclasses import dataclass, field
from typing import Literal, Optional

import pandas as pd

Verdict = Literal["PASS", "WARN", "FAIL", "N/A"]


@dataclass
class AttackResult:
    name: str
    verdict: Verdict
    summary: str                      # one plain-English sentence
    metrics: dict = field(default_factory=dict)
    curves: Optional[dict[str, pd.Series]] = None   # equity curves for charts, e.g. {"original": ..., "honest": ...}
