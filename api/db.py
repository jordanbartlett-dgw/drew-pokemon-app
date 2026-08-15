from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def open_read_only(db_path: Path) -> sqlite3.Connection:
    """Open the Pokédex database in read-only mode.

    Uses SQLite's mode=ro to block writes to the database file. Does NOT prevent
    ATTACH DATABASE, PRAGMA, or temp table statements; those are blocked by the
    SQL guard layer (api/sql_guard.py). Safe for concurrent access via query().
    """
    if not db_path.exists():
        raise FileNotFoundError(
            f"{db_path} does not exist. Run `uv run python -m ingest.sync` first."
        )
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def query(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Execute a SQL query and return results as a list of dictionaries.

    Reads are serialized via a module-level lock, making a single shared read-only
    connection safe for concurrent access across threads.
    """
    with _lock:
        return [dict(row) for row in conn.execute(sql, params)]
