from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from api.budget import (
    BUDGET_MESSAGE,
    PRICING_USD_PER_MTOK,
    ensure_schema,
    is_over_budget,
    price_of,
    record_usage,
    spent_today,
)
from api.store import create_conversation, load_turns, open_store, save_turn
from api.store import ensure_schema as ensure_store_schema


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


def test_save_turn_and_record_usage_share_a_lock_on_one_connection(pokedex_path):
    """Important 3: api/main.py hands the SAME sqlite3.Connection to both
    api/store.py's save_turn and api/budget.py's record_usage. If each module
    guarded it with its own independent lock, the two could interleave mid-write on
    that one connection -- both modules must serialize through api/lock.store_lock."""
    conn = open_store(pokedex_path)
    ensure_store_schema(conn)
    ensure_schema(conn)
    cid = create_conversation(conn, "concurrent chat")
    n = 30

    def _messages(text: str):
        return [
            ModelRequest(parts=[UserPromptPart(content=text)]),
            ModelResponse(parts=[TextPart(content="ok")]),
        ]

    def _turn(i: int) -> None:
        save_turn(conn, cid, f"q{i}", f"a{i}", [], _messages(f"q{i}"))
        record_usage(conn, "openai:gpt-5.6-luna", 1_000, 100)

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_turn, range(n)))

    turns = load_turns(conn, cid)
    assert len(turns) == n
    usage_rows = conn.execute("SELECT COUNT(*) AS c FROM usage_log").fetchone()
    assert usage_rows["c"] == n
