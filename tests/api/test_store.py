from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from api.models import ToolEvent
from api.store import (
    HISTORY_TURN_LIMIT,
    create_conversation,
    delete_conversation,
    ensure_schema,
    get_conversation_title,
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
    save_turn(conn, first, "q", "a", [], _messages("q"))
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


def test_load_history_returns_at_most_the_turn_limit(pokedex_path):
    conn = _store(pokedex_path)
    cid = create_conversation(conn, "long chat")
    turn_count = HISTORY_TURN_LIMIT + 3
    for i in range(turn_count):
        save_turn(conn, cid, f"question {i}", f"answer {i}", [], _messages(f"question {i}"))

    history = load_history(conn, cid)
    # Each _messages() turn contributes 2 ModelMessage entries (request + response).
    assert len(history) == HISTORY_TURN_LIMIT * 2

    # It's the MOST RECENT turns, not the oldest -- the last user prompt in history
    # should be the last turn saved, not the first.
    last_prompt = history[-2]
    assert isinstance(last_prompt, ModelRequest)
    assert last_prompt.parts[0].content == f"question {turn_count - 1}"


def test_save_turn_truncates_an_oversized_tool_return_but_keeps_tool_events_full(
    pokedex_path,
):
    conn = _store(pokedex_path)
    cid = create_conversation(conn, "sql chat")

    big_rows = [{"id": i, "name": f"pokemon-{i}"} for i in range(200)]
    big_result = {"sql": "SELECT * FROM v_pokemon", "rows": big_rows, "row_count": 200}
    messages = [
        ModelRequest(parts=[UserPromptPart(content="list every pokemon")]),
        ModelResponse(parts=[ToolCallPart("run_sql", {"sql": "..."}, tool_call_id="c1")]),
        ModelRequest(
            parts=[ToolReturnPart(tool_name="run_sql", content=big_result, tool_call_id="c1")]
        ),
    ]
    tool_events = [ToolEvent(tool_name="run_sql", args={"sql": "..."}, result=big_result)]

    save_turn(conn, cid, "list every pokemon", "Here they are!", tool_events, messages)

    row = conn.execute(
        "SELECT model_messages_json, tool_events_json FROM turns WHERE conversation_id = ?",
        (cid,),
    ).fetchone()

    stored_messages = json.loads(row["model_messages_json"])
    tool_return_parts = [
        part
        for message in stored_messages
        for part in message["parts"]
        if part.get("part_kind") == "tool-return"
    ]
    assert len(tool_return_parts) == 1
    assert tool_return_parts[0]["content"] == "[result truncated - 200 rows returned]"

    # tool_events_json, which the UI renders from, is untouched.
    turns = load_turns(conn, cid)
    assert turns[0].tool_events[0].result["row_count"] == 200
    assert len(turns[0].tool_events[0].result["rows"]) == 200


def test_list_conversations_excludes_zero_turn_conversations(pokedex_path):
    conn = _store(pokedex_path)
    empty = create_conversation(conn, "never answered")
    answered = create_conversation(conn, "answered")
    save_turn(conn, answered, "q", "a", [], _messages("q"))

    summaries = list_conversations(conn)
    assert [s.id for s in summaries] == [answered]
    assert empty not in [s.id for s in summaries]


def test_get_conversation_title_finds_a_zero_turn_conversation(pokedex_path):
    conn = _store(pokedex_path)
    cid = create_conversation(conn, "fresh chat")
    assert get_conversation_title(conn, cid) == "fresh chat"
    assert get_conversation_title(conn, 999) is None
