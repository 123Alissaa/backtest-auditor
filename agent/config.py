"""All endpoints and model IDs come from environment variables (.env).
Never hardcode model IDs in logic -- copy exact IDs from the Token Factory catalog."""
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    api_key: str = os.getenv("NEBIUS_API_KEY", "")
    base_url: str = os.getenv("NEBIUS_BASE_URL", "https://api.tokenfactory.us-central1.nebius.com/v1/")
    model_fast: str = os.getenv("MODEL_FAST", "")            # Nemotron Nano-class: code scanning, summaries
    model_reasoning: str = os.getenv("MODEL_REASONING", "")  # Nemotron Super/Ultra: audit planning, judgment
    project_id: str = os.getenv("NEBIUS_PROJECT_ID", "")    # Token Factory project; sent as the `Project` header to Sandboxes
    contree_url: str = os.getenv("CONTREE_URL", "https://api.tokenfactory.nebius.com/sandboxes/")
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")

    # Public-demo cost guards (agent/limits.py). Live runs are OFF unless explicitly enabled.
    live_runs_enabled: bool = os.getenv("LIVE_RUNS_ENABLED", "false").strip().lower() == "true"
    live_runs_until: str = os.getenv("LIVE_RUNS_UNTIL", "2026-12-15")        # no live runs after this date (UTC)
    daily_live_run_cap: int = int(os.getenv("DAILY_LIVE_RUN_CAP", "30"))     # across all visitors
    session_live_run_cap: int = int(os.getenv("SESSION_LIVE_RUN_CAP", "3"))  # per browser session
    max_code_bytes: int = int(os.getenv("MAX_CODE_BYTES", "20000"))
    daily_budget_usd: float = float(os.getenv("DAILY_BUDGET_USD", "0.15"))    # hard stop on measured LLM spend/day
    # Judging window (Dec 1-15): more headroom so judges don't hit "used up". Worst case from Oct 6:
    # 55 days x $0.15 + 15 days x $0.75 = $19.50 < ~$24.5 credit, so the balance can't go negative.
    judging_from: str = os.getenv("JUDGING_FROM", "2026-12-01")
    judging_until: str = os.getenv("JUDGING_UNTIL", "2026-12-15")
    judging_daily_budget_usd: float = float(os.getenv("JUDGING_DAILY_BUDGET_USD", "0.75"))
    judging_daily_run_cap: int = int(os.getenv("JUDGING_DAILY_RUN_CAP", "100"))
    judging_session_run_cap: int = int(os.getenv("JUDGING_SESSION_RUN_CAP", "5"))
    # USD per million tokens (input, output), from GET /v1/models?verbose=true on 2026-10-06.
    # Unknown models are priced at the most expensive Nemotron (Ultra) so the budget errs on the safe side.
    model_prices: tuple = (
        ("nvidia/nemotron-3-super-120b-a12b", 0.30, 0.90),
        ("nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B", 0.06, 0.24),
        ("nvidia/Nemotron-3-Ultra-550b-a55b", 1.00, 3.00),
    )
    fallback_price: tuple = (1.00, 3.00)
    max_price_rows: int = int(os.getenv("MAX_PRICE_ROWS", "10000"))


settings = Settings()
