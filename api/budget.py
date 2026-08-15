from __future__ import annotations

import sqlite3

from api.lock import store_lock as _lock

# Dollars per million tokens, (input, output).
# Source: https://developers.openai.com/api/docs/pricing, checked 2026-08-15.
# Update this table when the model changes or prices move.
PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "openai:gpt-5.6-luna": (0.20, 1.20),
    "openai:gpt-5-nano": (0.05, 0.40),
    "openai:gpt-5.4-nano": (0.20, 1.25),
    "openai:gpt-5-mini": (0.25, 2.00),
}

BUDGET_MESSAGE = "That's all the Pokémon questions for today, Drew. Come back tomorrow!"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL DEFAULT (date('now','localtime')),
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_usage_day ON usage_log(day);
"""


def _dearest_rate() -> tuple[float, float]:
    return max(PRICING_USD_PER_MTOK.values(), key=lambda rate: rate[0] + rate[1])


def price_of(model: str, input_tokens: int, output_tokens: int) -> float:
    """Cost in dollars. Unknown models are priced at the most expensive known rate."""
    input_rate, output_rate = PRICING_USD_PER_MTOK.get(model, _dearest_rate())
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


def ensure_schema(conn: sqlite3.Connection) -> None:
    with _lock:
        conn.executescript(_SCHEMA)
        conn.commit()


def record_usage(
    conn: sqlite3.Connection, model: str, input_tokens: int, output_tokens: int
) -> float:
    cost = price_of(model, input_tokens, output_tokens)
    with _lock:
        conn.execute(
            "INSERT INTO usage_log (model, input_tokens, output_tokens, cost_usd) "
            "VALUES (?, ?, ?, ?)",
            (model, input_tokens, output_tokens, cost),
        )
        conn.commit()
    return cost


def spent_today(conn: sqlite3.Connection) -> float:
    with _lock:
        row = conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM usage_log "
            "WHERE day = date('now','localtime')"
        ).fetchone()
    return float(row["total"])


def is_over_budget(conn: sqlite3.Connection, cap_usd: float) -> bool:
    return spent_today(conn) >= cap_usd
