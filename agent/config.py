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
    tavily_api_key: str = os.getenv("TAVILY_API_KEY", "")


settings = Settings()
