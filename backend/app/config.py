from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application configuration, overridable via environment variables."""

    anthropic_api_key: str = ""
    extraction_model: str = "claude-sonnet-4-6"
    adjudication_model: str = "claude-opus-4-8"

    policy_file: Path = BASE_DIR / "data" / "policy_terms.json"
    database_url: str = f"sqlite:///{BASE_DIR / 'claims.db'}"

    # When true, LLM classifiers are skipped entirely and only the
    # deterministic fallbacks run (used by the eval harness / CI).
    offline_mode: bool = False

    cors_origins: str = "http://localhost:3000"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
