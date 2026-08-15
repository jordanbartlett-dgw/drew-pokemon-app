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
    # The Pokédex: read-only, rebuilt from PokeAPI by `ingest.sync`, disposable.
    db_path: Path = Path("data/pokedex.db")
    # Drew's own data: conversations and the daily usage log. `ingest.sync` never
    # touches this file (it unlinks and rebuilds db_path only), so re-running the
    # ingest to refresh the Pokédex cannot destroy a conversation or the day's spend.
    store_path: Path = Field(default=Path("data/app.db"), alias="POKEDEX_STORE_PATH")
    images_dir: Path = Path("data/images")
    web_dist: Path = Path("web/build")

    # Cost control. See api/budget.py.
    daily_budget_usd: float = Field(default=0.25, alias="POKEDEX_DAILY_BUDGET_USD")
    request_limit: int = Field(default=8, alias="POKEDEX_REQUEST_LIMIT")
    tool_calls_limit: int = Field(default=12, alias="POKEDEX_TOOL_CALLS_LIMIT")
    # 60,000 tokens/question is about $0.07 worst case at the priciest known model
    # (api/budget.py's PRICING_USD_PER_MTOK) -- the $0.25/day cap in daily_budget_usd
    # is the real money control. This limit exists to stop a runaway tool loop, not
    # to ration tokens; 20,000 was too tight for a multi-turn conversation replaying
    # even a modestly sized history (see HISTORY_TURN_LIMIT in api/store.py).
    total_tokens_limit: int = Field(default=60_000, alias="POKEDEX_TOTAL_TOKENS_LIMIT")


@lru_cache
def get_settings() -> Settings:
    return Settings()
