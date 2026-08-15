from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import UsageLimits
from pydantic_ai.models import Model

from api.agent import PokedexDeps, build_agent
from api.budget import BUDGET_MESSAGE, is_over_budget, record_usage, spent_today
from api.budget import ensure_schema as ensure_budget_schema
from api.db import open_read_only, query
from api.sse import TurnRecorder, frame, stream_turn
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

APP_NAME = "Drew's Pokémon App"


class ChatRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: str = Field(min_length=1)
    conversation_id: int | None = None


def create_app(
    db_path: Path,
    images_dir: Path,
    model: str | Model,
    web_dist: Path | None = None,
    daily_budget_usd: float = 0.25,
    usage_limits: UsageLimits | None = None,
) -> FastAPI:
    app = FastAPI(title=APP_NAME)

    read_conn = open_read_only(db_path)
    store_conn = open_store(db_path)
    ensure_schema(store_conn)
    ensure_budget_schema(store_conn)
    agent = build_agent(model)
    model_id = model if isinstance(model, str) else getattr(model, "model_name", "unknown")

    images_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/images", StaticFiles(directory=images_dir), name="images")

    @app.get("/api/health")
    def health() -> dict[str, object]:
        count = query(read_conn, "SELECT COUNT(*) AS n FROM v_pokemon")[0]["n"]
        return {
            "status": "ok",
            "app": APP_NAME,
            "pokemon_count": count,
            "model": model_id,
            "spent_today_usd": round(spent_today(store_conn), 6),
            "daily_budget_usd": daily_budget_usd,
        }

    @app.get("/api/conversations")
    def conversations() -> list[dict[str, object]]:
        return [summary.model_dump() for summary in list_conversations(store_conn)]

    @app.get("/api/conversations/{conversation_id}")
    def conversation(conversation_id: int) -> dict[str, object]:
        summaries = [s for s in list_conversations(store_conn) if s.id == conversation_id]
        if not summaries:
            raise HTTPException(status_code=404, detail="No such conversation")
        return {
            "conversation": summaries[0].model_dump(),
            "turns": [turn.model_dump() for turn in load_turns(store_conn, conversation_id)],
        }

    @app.delete("/api/conversations/{conversation_id}", status_code=204)
    def remove_conversation(conversation_id: int) -> None:
        delete_conversation(store_conn, conversation_id)

    @app.post("/api/chat")
    def chat(request: ChatRequest) -> StreamingResponse:
        message = request.message.strip()
        if not message:
            raise HTTPException(status_code=422, detail="Ask me something about Pokémon!")

        conversation_id = request.conversation_id
        if conversation_id is None:
            conversation_id = create_conversation(store_conn, title_from(message))
            title = title_from(message)
        else:
            summaries = [s for s in list_conversations(store_conn) if s.id == conversation_id]
            if not summaries:
                raise HTTPException(status_code=404, detail="No such conversation")
            title = summaries[0].title

        async def body() -> AsyncIterator[str]:
            yield frame("start", {"conversation_id": conversation_id, "title": title})

            if is_over_budget(store_conn, daily_budget_usd):
                yield frame("limit", {"message": BUDGET_MESSAGE})
                yield frame("done", {"conversation_id": conversation_id})
                return

            recorder = TurnRecorder()
            history = load_history(store_conn, conversation_id)
            async for chunk in stream_turn(
                agent, PokedexDeps(conn=read_conn), message, history, recorder, usage_limits
            ):
                yield chunk

            if recorder.input_tokens or recorder.output_tokens:
                record_usage(store_conn, model_id, recorder.input_tokens, recorder.output_tokens)

            if recorder.new_messages:
                save_turn(
                    store_conn,
                    conversation_id,
                    message,
                    recorder.text,
                    recorder.tool_events,
                    recorder.new_messages,
                )
            yield frame("done", {"conversation_id": conversation_id})

        return StreamingResponse(
            body(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Mounted last, at the root, so it cannot shadow /api or /images.
    if web_dist is not None and web_dist.is_dir():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    return app
