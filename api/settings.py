from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets arrive from Infisical via `infisical run --`."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    openai_api_key: SecretStr
    openai_model: str = Field(default="openai:gpt-5.6-luna", alias="POKEDEX_OPENAI_MODEL")
    db_path: Path = Path("data/pokedex.db")
    images_dir: Path = Path("data/images")
    web_dist: Path = Path("web/build")

    # Cost control. See api/budget.py.
    daily_budget_usd: float = Field(default=0.25, alias="POKEDEX_DAILY_BUDGET_USD")
    request_limit: int = Field(default=8, alias="POKEDEX_REQUEST_LIMIT")
    tool_calls_limit: int = Field(default=12, alias="POKEDEX_TOOL_CALLS_LIMIT")
    total_tokens_limit: int = Field(default=20_000, alias="POKEDEX_TOTAL_TOKENS_LIMIT")


@lru_cache
def get_settings() -> Settings:
    return Settings()
