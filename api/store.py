from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from pydantic_ai import ModelMessagesTypeAdapter
from pydantic_ai.messages import ModelMessage
from pydantic_core import to_jsonable_python

from api.lock import store_lock as _lock
from api.models import ConversationSummary, StoredTurn, ToolEvent

TITLE_MAX_LENGTH = 60

# Replay only the most recent N turns as model history. Each turn's full
# model_messages_json (including complete tool-return payloads) gets re-sent on
# EVERY model request in a run, and UsageLimits.total_tokens_limit (api/settings.py)
# counts total tokens across all of them -- so an unbounded history eventually blows
# the limit no matter what Drew asks next, permanently bricking the conversation.
# 4 turns keeps a real back-and-forth (e.g. "build me a team" + a follow-up) working
# without carrying the whole conversation's tool-call history forward forever.
HISTORY_TURN_LIMIT = 4

# Cap a single tool-return part's serialized content before persisting it to
# model_messages_json. api/tools.py's run_sql can return up to sql_guard.MAX_ROWS
# (200) rows, which alone can serialize to ~28k tokens -- more than the whole
# per-run UsageLimits.total_tokens_limit -- poisoning every future request in the
# conversation. tool_events_json (loaded by load_turns, not load_history) already
# carries the full result for the UI, so the model's replayed history doesn't need it.
MAX_TOOL_RETURN_CHARS = 4_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_text TEXT NOT NULL,
    assistant_text TEXT NOT NULL,
    tool_events_json TEXT NOT NULL DEFAULT '[]',
    model_messages_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_turns_conversation ON turns(conversation_id);
"""


def open_store(db_path: Path) -> sqlite3.Connection:
    """Open a writable connection to the conversation store.

    check_same_thread=False lets this single connection be shared across FastAPI's
    threadpool, but that only disables sqlite3's same-thread assertion; it does not
    make the connection safe for concurrent use on its own. The connection is safe
    to share across threads provided ALL access goes through this module's
    functions, which serialize every statement (reads and writes) via a module-level
    lock, matching the pattern api/db.py uses for the read-only Pokédex connection.
    """
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    with _lock:
        conn.executescript(_SCHEMA)
        conn.commit()


def title_from(user_text: str) -> str:
    collapsed = " ".join(user_text.split())
    if len(collapsed) <= TITLE_MAX_LENGTH:
        return collapsed
    return collapsed[: TITLE_MAX_LENGTH - 1].rstrip() + "…"


def create_conversation(conn: sqlite3.Connection, title: str) -> int:
    with _lock:
        cursor = conn.execute("INSERT INTO conversations (title) VALUES (?)", (title,))
        conn.commit()
        return int(cursor.lastrowid)


def list_conversations(conn: sqlite3.Connection) -> list[ConversationSummary]:
    """Conversations with at least one saved turn, newest first.

    A turn that persists nothing (over-budget, disconnect before any token, early
    error) leaves a zero-turn conversation row. Showing it in the sidebar titled with
    Drew's question, only for tapping it to render the empty state, is worse than not
    showing it at all -- it saves nothing worth resuming.
    """
    with _lock:
        rows = conn.execute(
            """
            SELECT c.id, c.title, c.created_at, c.updated_at,
                   (SELECT COUNT(*) FROM turns t WHERE t.conversation_id = c.id) AS turn_count
            FROM conversations c
            WHERE EXISTS (SELECT 1 FROM turns t WHERE t.conversation_id = c.id)
            ORDER BY c.updated_at DESC, c.id DESC
            """
        ).fetchall()
    return [ConversationSummary(**dict(row)) for row in rows]


def get_conversation_title(conn: sqlite3.Connection, conversation_id: int) -> str | None:
    """The title of any conversation row, including a fresh zero-turn one.

    Used to validate a client-supplied conversation_id on /api/chat's continuation
    path. Deliberately NOT `list_conversations`, which hides zero-turn conversations
    from the sidebar (see its docstring) -- a conversation whose first turn hasn't
    saved yet (e.g. the daily budget tripped before any tokens were spent) must still
    be a valid target to continue, not a 404.
    """
    with _lock:
        row = conn.execute(
            "SELECT title FROM conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
    return row["title"] if row else None


def load_turns(conn: sqlite3.Connection, conversation_id: int) -> list[StoredTurn]:
    with _lock:
        rows = conn.execute(
            "SELECT id, user_text, assistant_text, tool_events_json, created_at "
            "FROM turns WHERE conversation_id = ? ORDER BY id",
            (conversation_id,),
        ).fetchall()
    return [
        StoredTurn(
            id=row["id"],
            user_text=row["user_text"],
            assistant_text=row["assistant_text"],
            tool_events=[ToolEvent(**e) for e in json.loads(row["tool_events_json"])],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def load_history(conn: sqlite3.Connection, conversation_id: int) -> list[ModelMessage]:
    """The most recent HISTORY_TURN_LIMIT turns, oldest first, as model history."""
    with _lock:
        rows = conn.execute(
            "SELECT model_messages_json FROM turns WHERE conversation_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (conversation_id, HISTORY_TURN_LIMIT),
        ).fetchall()
    history: list[ModelMessage] = []
    for row in reversed(rows):
        history.extend(ModelMessagesTypeAdapter.validate_json(row["model_messages_json"]))
    return history


def _truncate_tool_returns(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replace oversized tool-return content with a short marker, in place.

    Operates on the jsonable-python form of a list of ModelMessage (as produced by
    `to_jsonable_python`), each with a "parts" list of part dicts discriminated by
    "part_kind". Only "tool-return" parts are touched; tool calls and text are
    already small. tool_events_json (see save_turn) still carries the untruncated
    result for the UI.
    """
    for message in messages:
        for part in message.get("parts") or []:
            if not isinstance(part, dict) or part.get("part_kind") != "tool-return":
                continue
            content = part.get("content")
            serialized = json.dumps(content)
            if len(serialized) <= MAX_TOOL_RETURN_CHARS:
                continue
            row_count = content.get("row_count") if isinstance(content, dict) else None
            if row_count is not None:
                part["content"] = f"[result truncated - {row_count} rows returned]"
            else:
                part["content"] = f"[result truncated - {len(serialized)} characters]"
    return messages


def save_turn(
    conn: sqlite3.Connection,
    conversation_id: int,
    user_text: str,
    assistant_text: str,
    tool_events: list[ToolEvent],
    new_messages: list[ModelMessage],
) -> int:
    truncated_messages = _truncate_tool_returns(to_jsonable_python(new_messages))
    with _lock:
        cursor = conn.execute(
            "INSERT INTO turns (conversation_id, user_text, assistant_text, "
            "tool_events_json, model_messages_json) VALUES (?, ?, ?, ?, ?)",
            (
                conversation_id,
                user_text,
                assistant_text,
                json.dumps([e.model_dump() for e in tool_events]),
                json.dumps(truncated_messages),
            ),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
            (conversation_id,),
        )
        conn.commit()
        return int(cursor.lastrowid)


def delete_conversation(conn: sqlite3.Connection, conversation_id: int) -> None:
    with _lock:
        # PRAGMA foreign_keys = ON (set in open_store) already makes ON DELETE CASCADE
        # remove these rows; this explicit delete is belt-and-braces, not load-bearing.
        conn.execute("DELETE FROM turns WHERE conversation_id = ?", (conversation_id,))
        conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
        conn.commit()
