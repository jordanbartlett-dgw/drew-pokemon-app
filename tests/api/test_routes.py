from __future__ import annotations

import json

import httpx
import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from api.budget import ensure_schema as ensure_budget_schema
from api.budget import record_usage
from api.main import create_app
from api.store import open_store

pytestmark = pytest.mark.anyio

# `stream_turn` always drives `agent.run_stream_events`, which takes pydantic-ai's
# streaming request path. On 2.31.0, `FunctionModel.request_stream` hard-requires a
# `stream_function` (see tests/api/test_sse.py) — a plain `function=` script is not
# enough here. Each script below ships a matching `stream_*` twin.


def _script(messages: list[ModelMessage], info: AgentInfo):
    if len(messages) == 1:
        return ModelResponse(parts=[ToolCallPart("find_pokemon", {"name_or_id": "pikachu"})])
    return ModelResponse(parts=[TextPart("Pikachu is quick!")])


async def _stream_script(messages: list[ModelMessage], info: AgentInfo):
    if len(messages) == 1:
        yield {
            0: DeltaToolCall(
                name="find_pokemon",
                json_args=json.dumps({"name_or_id": "pikachu"}),
                tool_call_id="call_1",
            )
        }
    else:
        yield "Pikachu is quick!"


@pytest.fixture
def client(pokedex_path, tmp_path):
    app = create_app(
        db_path=pokedex_path,
        images_dir=tmp_path,
        model=FunctionModel(_script, stream_function=_stream_script),
    )
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _events(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        lines = block.split("\n")
        out.append((lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))))
    return out


async def test_health_reports_pokemon_count(client):
    async with client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["pokemon_count"] == 4


async def test_chat_streams_and_persists(client):
    async with client:
        response = await client.post("/api/chat", json={"message": "Who is Pikachu?"})
        events = _events(response.text)

        assert events[0][0] == "start"
        conversation_id = events[0][1]["conversation_id"]
        assert events[0][1]["title"] == "Who is Pikachu?"
        assert any(name == "tool" for name, _ in events)
        assert "".join(d["text"] for n, d in events if n == "token") == "Pikachu is quick!"
        assert events[-1][0] == "done"

        detail = await client.get(f"/api/conversations/{conversation_id}")

    body = detail.json()
    assert body["turns"][0]["assistant_text"] == "Pikachu is quick!"
    assert body["turns"][0]["tool_events"][0]["tool_name"] == "find_pokemon"


async def test_chat_continues_an_existing_conversation(client):
    async with client:
        first = await client.post("/api/chat", json={"message": "Who is Pikachu?"})
        conversation_id = _events(first.text)[0][1]["conversation_id"]

        await client.post(
            "/api/chat", json={"message": "And Raichu?", "conversation_id": conversation_id}
        )
        listing = await client.get("/api/conversations")
        detail = await client.get(f"/api/conversations/{conversation_id}")

    assert len(listing.json()) == 1
    assert listing.json()[0]["turn_count"] == 2
    assert len(detail.json()["turns"]) == 2


async def test_unknown_conversation_is_404(client):
    async with client:
        response = await client.get("/api/conversations/999")
    assert response.status_code == 404


async def test_delete_conversation(client):
    async with client:
        created = await client.post("/api/chat", json={"message": "Who is Pikachu?"})
        conversation_id = _events(created.text)[0][1]["conversation_id"]
        deleted = await client.delete(f"/api/conversations/{conversation_id}")
        listing = await client.get("/api/conversations")

    assert deleted.status_code == 204
    assert listing.json() == []


async def test_empty_message_is_rejected(client):
    async with client:
        response = await client.post("/api/chat", json={"message": "   "})
    assert response.status_code == 422


async def test_health_reports_budget(client):
    async with client:
        body = (await client.get("/api/health")).json()
    assert body["daily_budget_usd"] == 0.25
    assert body["spent_today_usd"] == 0.0


async def test_over_budget_never_calls_the_model(pokedex_path, tmp_path):
    calls: list[int] = []

    def counting(messages, info):
        calls.append(1)
        return ModelResponse(parts=[TextPart("should not happen")])

    async def stream_counting(messages, info):
        calls.append(1)
        yield "should not happen"

    app = create_app(
        db_path=pokedex_path,
        images_dir=tmp_path,
        model=FunctionModel(counting, stream_function=stream_counting),
        daily_budget_usd=0.0001,
    )
    conn = open_store(pokedex_path)
    ensure_budget_schema(conn)
    record_usage(conn, "openai:gpt-5.6-luna", 1_000_000, 0)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat", json={"message": "Who is Pikachu?"})

    events = _events(response.text)
    assert [name for name, _ in events] == ["start", "limit", "done"]
    assert "tomorrow" in events[1][1]["message"].lower()
    assert calls == []


async def test_usage_is_recorded_after_a_turn(client, pokedex_path):
    async with client:
        await client.post("/api/chat", json={"message": "Who is Pikachu?"})
        body = (await client.get("/api/health")).json()
    assert body["spent_today_usd"] > 0
