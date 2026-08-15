from __future__ import annotations

from pydantic_ai import UsageLimits

from api.main import create_app
from api.settings import get_settings

settings = get_settings()

app = create_app(
    db_path=settings.db_path,
    images_dir=settings.images_dir,
    model=settings.openai_model,
    web_dist=settings.web_dist,
    daily_budget_usd=settings.daily_budget_usd,
    usage_limits=UsageLimits(
        request_limit=settings.request_limit,
        tool_calls_limit=settings.tool_calls_limit,
        total_tokens_limit=settings.total_tokens_limit,
    ),
)
