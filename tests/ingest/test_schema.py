from __future__ import annotations

import sqlite3

from ingest.schema import TABLES, apply_schema


def test_apply_schema_creates_every_table():
    conn = sqlite3.connect(":memory:")
    apply_schema(conn)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(TABLES) <= names


def test_pokemon_table_has_expected_columns():
    conn = sqlite3.connect(":memory:")
    apply_schema(conn)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(pokemon)")]
    assert cols == [
        "id",
        "identifier",
        "species_id",
        "height",
        "weight",
        "base_experience",
        "order_",
        "is_default",
    ]


def test_type_efficacy_table_has_expected_columns():
    conn = sqlite3.connect(":memory:")
    apply_schema(conn)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(type_efficacy)")]
    assert cols == ["damage_type_id", "target_type_id", "damage_factor"]
