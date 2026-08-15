from __future__ import annotations

import json

import httpx
import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from api.budget import ensure_schema as ensure_budget_schema
from api.budget import record_usage
from api.main import ChatRequest, create_app
from api.store import load_turns, open_store

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


@pytest.fixture
def client_with_web_dist(pokedex_path, tmp_path):
    """A client whose app has a built frontend mounted, like the Minisforum deploy."""
    web_dist = tmp_path / "build"
    web_dist.mkdir()
    (web_dist / "index.html").write_text("<html><body>drew's pokemon app</body></html>")
    images_dir = tmp_path / "images"
    images_dir.mkdir()
    app = create_app(
        db_path=pokedex_path,
        images_dir=images_dir,
        model=FunctionModel(_script, stream_function=_stream_script),
        web_dist=web_dist,
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


async def test_unknown_route_without_web_dist_stays_a_plain_404(client):
    """No `web_dist` mounted (the default in most tests) -- nothing tries to
    read a nonexistent index.html, and an unmatched route is a plain 404."""
    async with client:
        response = await client.get("/some/unknown/path")
    assert response.status_code == 404


async def test_unknown_deep_link_serves_the_app_shell_with_web_dist(client_with_web_dist):
    """SPA fallback: an unmatched path, like Drew's iPad reloading on a client-side
    route, gets the built app's index.html with a 200, not a 404."""
    async with client_with_web_dist as client:
        response = await client.get("/some/unknown/path")
    assert response.status_code == 200
    assert "drew's pokemon app" in response.text.lower()
    assert response.headers["content-type"].startswith("text/html")


async def test_unknown_api_route_is_still_json_404_with_web_dist(client_with_web_dist):
    """The important guardrail: the SPA fallback must not swallow API 404s.
    If it did, every frontend error path would silently get a web page back
    instead of an error it can detect."""
    async with client_with_web_dist as client:
        response = await client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert "detail" in response.json()


async def test_unknown_conversation_is_still_json_404_with_web_dist(client_with_web_dist):
    """Same guardrail, exercised through the existing conversations 404 path
    rather than a synthetic unmatched route."""
    async with client_with_web_dist as client:
        response = await client.get("/api/conversations/999")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


async def test_missing_image_is_404_not_the_app_shell(client_with_web_dist):
    async with client_with_web_dist as client:
        response = await client.get("/images/does-not-exist.png")
    assert response.status_code == 404
    assert not response.headers["content-type"].startswith("text/html")


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


async def test_happy_path_bills_exactly_one_usage_row(client, pokedex_path):
    async with client:
        await client.post("/api/chat", json={"message": "Who is Pikachu?"})
    store = open_store(pokedex_path)
    rows = store.execute("SELECT COUNT(*) AS n FROM usage_log").fetchone()
    assert rows["n"] == 1


async def test_disconnect_mid_turn_still_bills_and_persists(pokedex_path, tmp_path):
    """Simulate a client (Drew's iPad) walking away mid-answer.

    `httpx.ASGITransport` cannot express a genuine mid-stream disconnect: its
    `handle_async_request` awaits the whole ASGI app call to completion before
    building a `Response` at all (see `httpx._transports.asgi.ASGITransport`),
    so consuming a few lines and closing the stream never actually interrupts
    the server-side generator — the turn always finishes first. Cancelling the
    outer asyncio task is not deterministic either: on this ASGI spec version
    Starlette's `StreamingResponse.__call__` runs `stream_response` inside a
    separate task group, so the timing of when cancellation reaches `body()`
    depends on anyio internals, not on this test.

    The deterministic equivalent used here: call the `/api/chat` route's
    endpoint function directly (a plain Python function call, no ASGI
    machinery) to get the `StreamingResponse` it builds, pull a couple of real
    frames from its `body_iterator` (the app's `body()` async generator), then
    `.aclose()` it mid-turn. That is exactly the `GeneratorExit` Starlette
    throws into an abandoned response body when a real client disconnects.
    """
    app = create_app(
        db_path=pokedex_path,
        images_dir=tmp_path,
        model=FunctionModel(_script, stream_function=_stream_script),
    )
    route = next(r for r in app.routes if getattr(r, "path", None) == "/api/chat")
    chat = route.endpoint

    response = chat(ChatRequest(message="Who is Pikachu?"))
    gen = response.body_iterator

    start_frame = await gen.__anext__()
    conversation_id = json.loads(start_frame.split("\n")[1].removeprefix("data: "))[
        "conversation_id"
    ]
    tool_frame = await gen.__anext__()
    assert tool_frame.startswith("event: tool")

    # Walk away before the model's final answer streams back or completes.
    await gen.aclose()

    store = open_store(pokedex_path)
    usage_rows = store.execute("SELECT * FROM usage_log").fetchall()
    assert len(usage_rows) == 1
    assert usage_rows[0]["input_tokens"] > 0

    turns = load_turns(store, conversation_id)
    assert len(turns) == 1
    assert turns[0].tool_events[0].tool_name == "find_pokemon"
