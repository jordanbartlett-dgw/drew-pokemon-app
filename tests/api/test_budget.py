from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from api.budget import (
    BUDGET_MESSAGE,
    PRICING_USD_PER_MTOK,
    ensure_schema,
    is_over_budget,
    price_of,
    record_usage,
    spent_today,
)
from api.store import open_store


def _conn(pokedex_path):
    conn = open_store(pokedex_path)
    ensure_schema(conn)
    return conn


def test_pricing_table_has_the_default_model():
    assert PRICING_USD_PER_MTOK["openai:gpt-5.6-luna"] == (0.20, 1.20)


def test_price_of_known_model():
    # 1M input at $0.20 plus 1M output at $1.20
    assert price_of("openai:gpt-5.6-luna", 1_000_000, 1_000_000) == 1.40


def test_price_of_a_realistic_turn_is_about_a_tenth_of_a_cent():
    cost = price_of("openai:gpt-5.6-luna", 4_000, 300)
    assert 0.001 < cost < 0.002


def test_unknown_model_is_priced_at_the_most_expensive_rate():
    dearest = max(PRICING_USD_PER_MTOK.values(), key=lambda rate: rate[0] + rate[1])
    assert price_of("openai:something-new", 1_000_000, 1_000_000) == sum(dearest)


def test_record_usage_accumulates_across_turns(pokedex_path):
    conn = _conn(pokedex_path)
    assert spent_today(conn) == 0.0
    first = record_usage(conn, "openai:gpt-5.6-luna", 4_000, 300)
    second = record_usage(conn, "openai:gpt-5.6-luna", 4_000, 300)
    assert round(spent_today(conn), 8) == round(first + second, 8)


def test_is_over_budget_only_once_the_cap_is_reached(pokedex_path):
    conn = _conn(pokedex_path)
    assert is_over_budget(conn, 0.25) is False
    record_usage(conn, "openai:gpt-5.6-luna", 1_000_000, 0)  # $0.20
    assert is_over_budget(conn, 0.25) is False
    record_usage(conn, "openai:gpt-5.6-luna", 1_000_000, 0)  # $0.40 total
    assert is_over_budget(conn, 0.25) is True


def test_yesterdays_spend_does_not_count(pokedex_path):
    conn = _conn(pokedex_path)
    conn.execute(
        "INSERT INTO usage_log (day, model, input_tokens, output_tokens, cost_usd) "
        "VALUES (date('now','localtime','-1 day'), 'openai:gpt-5.6-luna', 1000000, 0, 0.20)"
    )
    conn.commit()
    assert spent_today(conn) == 0.0


def test_budget_message_is_kid_friendly():
    assert "Drew" in BUDGET_MESSAGE
    assert "tomorrow" in BUDGET_MESSAGE.lower()


def test_float_accumulation_over_many_realistic_turns_stays_sane(pokedex_path):
    conn = _conn(pokedex_path)
    n = 350  # roughly the cap's worth of questions at the measured real-turn cost
    total = 0.0
    for _ in range(n):
        total += record_usage(conn, "openai:gpt-5.6-luna", 2_627, 151)
    assert round(spent_today(conn), 6) == round(total, 6)
    # ~350 turns at ~$0.0007 should land close to the $0.25 default cap.
    assert 0.20 < spent_today(conn) < 0.30
    assert is_over_budget(conn, spent_today(conn)) is True
    assert is_over_budget(conn, spent_today(conn) + 0.01) is False


def test_record_usage_is_safe_under_concurrent_writers(pokedex_path):
    conn = _conn(pokedex_path)
    n = 40

    def _record(_: int) -> float:
        return record_usage(conn, "openai:gpt-5.6-luna", 1_000, 100)

    with ThreadPoolExecutor(max_workers=8) as pool:
        costs = list(pool.map(_record, range(n)))

    row = conn.execute("SELECT COUNT(*) AS c FROM usage_log").fetchone()
    assert row["c"] == n
    assert round(spent_today(conn), 8) == round(sum(costs), 8)
