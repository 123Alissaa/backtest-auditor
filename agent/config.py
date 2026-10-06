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
    max_price_rows: int = int(os.getenv("MAX_PRICE_ROWS", "10000"))


settings = Settings()
