from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from api.models import ToolEvent
from api.store import (
    create_conversation,
    delete_conversation,
    ensure_schema,
    list_conversations,
    load_history,
    load_turns,
    open_store,
    save_turn,
    title_from,
)


def _store(pokedex_path):
    conn = open_store(pokedex_path)
    ensure_schema(conn)
    return conn


def _messages(text: str):
    return [
        ModelRequest(parts=[UserPromptPart(content=text)]),
        ModelResponse(parts=[TextPart(content="ok")]),
    ]


def test_title_from_truncates_long_questions():
    assert title_from("Who is Pikachu?") == "Who is Pikachu?"
    assert len(title_from("x" * 200)) <= 60


def test_save_and_load_a_turn(pokedex_path):
    conn = _store(pokedex_path)
    cid = create_conversation(conn, "Pikachu chat")
    events = [
        ToolEvent(tool_name="find_pokemon", args={"name_or_id": "pikachu"}, result={"id": 25})
    ]
    save_turn(conn, cid, "Who is Pikachu?", "A mouse!", events, _messages("Who is Pikachu?"))

    turns = load_turns(conn, cid)
    assert len(turns) == 1
    assert turns[0].user_text == "Who is Pikachu?"
    assert turns[0].assistant_text == "A mouse!"
    assert turns[0].tool_events[0].tool_name == "find_pokemon"


def test_history_round_trips_pydantic_ai_messages(pokedex_path):
    conn = _store(pokedex_path)
    cid = create_conversation(conn, "chat")
    save_turn(conn, cid, "one", "ok", [], _messages("one"))
    save_turn(conn, cid, "two", "ok", [], _messages("two"))

    history = load_history(conn, cid)
    assert len(history) == 4
    assert isinstance(history[0], ModelRequest)


def test_list_conversations_counts_turns_newest_first(pokedex_path):
    conn = _store(pokedex_path)
    first = create_conversation(conn, "first")
    second = create_conversation(conn, "second")
    save_turn(conn, second, "q", "a", [], _messages("q"))

    summaries = list_conversations(conn)
    assert [s.id for s in summaries] == [second, first]
    assert summaries[0].turn_count == 1


def test_delete_removes_conversation_and_turns(pokedex_path):
    conn = _store(pokedex_path)
    cid = create_conversation(conn, "chat")
    save_turn(conn, cid, "q", "a", [], _messages("q"))
    delete_conversation(conn, cid)
    assert list_conversations(conn) == []
    assert load_turns(conn, cid) == []


def test_save_turn_is_safe_under_concurrent_writers(pokedex_path):
    conn = _store(pokedex_path)
    cid = create_conversation(conn, "chat")
    n = 25

    def _save(i: int) -> None:
        save_turn(conn, cid, f"question {i}", f"answer {i}", [], _messages(f"question {i}"))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_save, range(n)))

    turns = load_turns(conn, cid)
    assert len(turns) == n
    user_texts = {t.user_text for t in turns}
    assert user_texts == {f"question {i}" for i in range(n)}

    summaries = list_conversations(conn)
    assert summaries[0].id == cid
    assert summaries[0].turn_count == n
