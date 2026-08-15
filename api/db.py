from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def open_read_only(db_path: Path) -> sqlite3.Connection:
    """Open the Pokédex read-only. Writes raise sqlite3.OperationalError."""
    if not db_path.exists():
        raise FileNotFoundError(
            f"{db_path} does not exist. Run `uv run python -m ingest.sync` first."
        )
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def query(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params)]
