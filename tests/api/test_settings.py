from __future__ import annotations

from pathlib import Path

from api.settings import Settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("POKEDEX_OPENAI_MODEL", "openai:gpt-test")
    settings = Settings()
    assert settings.openai_api_key.get_secret_value() == "sk-test"
    assert settings.openai_model == "openai:gpt-test"
    assert settings.db_path == Path("data/pokedex.db")
    assert settings.images_dir == Path("data/images")
    assert settings.web_dist == Path("web/build")


def test_settings_model_has_provider_prefix(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("POKEDEX_OPENAI_MODEL", raising=False)
    assert ":" in Settings().openai_model


def test_limit_defaults_are_conservative(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    settings = Settings()
    assert settings.daily_budget_usd == 0.25
    assert settings.request_limit == 8
    assert settings.tool_calls_limit == 12
    assert settings.total_tokens_limit == 20_000
