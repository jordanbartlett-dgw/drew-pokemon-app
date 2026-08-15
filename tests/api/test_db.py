from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest

from api.db import open_read_only, query


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "pokedex.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE v_pokemon (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO v_pokemon VALUES (25, 'Pikachu')")
    conn.commit()
    conn.close()
    return path


def test_query_returns_dicts(db_path):
    conn = open_read_only(db_path)
    assert query(conn, "SELECT * FROM v_pokemon") == [{"id": 25, "name": "Pikachu"}]


def test_query_accepts_parameters(db_path):
    conn = open_read_only(db_path)
    rows = query(conn, "SELECT name FROM v_pokemon WHERE id = ?", (25,))
    assert rows == [{"name": "Pikachu"}]


def test_connection_rejects_writes(db_path):
    conn = open_read_only(db_path)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO v_pokemon VALUES (1, 'Bulbasaur')")


def test_open_read_only_raises_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        open_read_only(tmp_path / "nope.db")


def test_concurrent_queries_are_serialized(db_path):
    """Verify that concurrent query() calls on a shared connection are safe.

    This test runs 8 threads, each executing 50 queries concurrently. Without
    the module-level lock in query(), SQLite would raise ProgrammingError or
    return inconsistent results under concurrent load.
    """
    conn = open_read_only(db_path)
    expected = [{"id": 25, "name": "Pikachu"}]
    results = []

    def worker():
        for _ in range(50):
            result = query(conn, "SELECT * FROM v_pokemon")
            results.append(result)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker) for _ in range(8)]
        for future in as_completed(futures):
            future.result()

    assert len(results) == 400
    assert all(r == expected for r in results)
