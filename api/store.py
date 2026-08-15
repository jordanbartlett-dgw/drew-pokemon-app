from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pydantic_ai import ModelMessagesTypeAdapter
from pydantic_ai.messages import ModelMessage
from pydantic_core import to_jsonable_python

from api.models import ConversationSummary, StoredTurn, ToolEvent

TITLE_MAX_LENGTH = 60

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
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def title_from(user_text: str) -> str:
    collapsed = " ".join(user_text.split())
    if len(collapsed) <= TITLE_MAX_LENGTH:
        return collapsed
    return collapsed[: TITLE_MAX_LENGTH - 1].rstrip() + "…"


def create_conversation(conn: sqlite3.Connection, title: str) -> int:
    cursor = conn.execute("INSERT INTO conversations (title) VALUES (?)", (title,))
    conn.commit()
    return int(cursor.lastrowid)


def list_conversations(conn: sqlite3.Connection) -> list[ConversationSummary]:
    rows = conn.execute(
        """
        SELECT c.id, c.title, c.created_at, c.updated_at,
               (SELECT COUNT(*) FROM turns t WHERE t.conversation_id = c.id) AS turn_count
        FROM conversations c
        ORDER BY c.updated_at DESC, c.id DESC
        """
    ).fetchall()
    return [ConversationSummary(**dict(row)) for row in rows]


def load_turns(conn: sqlite3.Connection, conversation_id: int) -> list[StoredTurn]:
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
    rows = conn.execute(
        "SELECT model_messages_json FROM turns WHERE conversation_id = ? ORDER BY id",
        (conversation_id,),
    ).fetchall()
    history: list[ModelMessage] = []
    for row in rows:
        history.extend(ModelMessagesTypeAdapter.validate_json(row["model_messages_json"]))
    return history


def save_turn(
    conn: sqlite3.Connection,
    conversation_id: int,
    user_text: str,
    assistant_text: str,
    tool_events: list[ToolEvent],
    new_messages: list[ModelMessage],
) -> int:
    cursor = conn.execute(
        "INSERT INTO turns (conversation_id, user_text, assistant_text, "
        "tool_events_json, model_messages_json) VALUES (?, ?, ?, ?, ?)",
        (
            conversation_id,
            user_text,
            assistant_text,
            json.dumps([e.model_dump() for e in tool_events]),
            json.dumps(to_jsonable_python(new_messages)),
        ),
    )
    conn.execute(
        "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
        (conversation_id,),
    )
    conn.commit()
    return int(cursor.lastrowid)


def delete_conversation(conn: sqlite3.Connection, conversation_id: int) -> None:
    conn.execute("DELETE FROM turns WHERE conversation_id = ?", (conversation_id,))
    conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    conn.commit()
