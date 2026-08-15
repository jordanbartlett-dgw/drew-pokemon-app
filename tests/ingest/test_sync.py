from __future__ import annotations

import sqlite3

from ingest.schema import TABLES, apply_schema
from ingest.sync import verify
from ingest.views import apply_views


def _seed(db_path, speed: int = 90, factor: int = 200):
    conn = sqlite3.connect(db_path)
    apply_schema(conn)
    conn.executescript(
        f"""
        INSERT INTO pokemon VALUES (25,'pikachu',25,4,60,112,32,1);
        INSERT INTO pokemon_species (id,identifier,generation_id,evolution_chain_id)
            VALUES (25,'pikachu',1,10);
        INSERT INTO pokemon_species_names VALUES (25,9,'Pikachu','Mouse Pokémon');
        INSERT INTO types VALUES (13,'electric',1,3);
        INSERT INTO types VALUES (11,'water',1,3);
        INSERT INTO types VALUES (10,'fire',1,3);
        INSERT INTO type_names VALUES (13,9,'Electric'),(11,9,'Water'),(10,9,'Fire');
        INSERT INTO pokemon_types VALUES (25,13,1);
        INSERT INTO type_efficacy VALUES (11,10,{factor});
        INSERT INTO pokemon_stats VALUES
            (25,1,35,0),(25,2,55,0),(25,3,40,0),(25,4,50,0),(25,5,50,0),(25,6,{speed},0);
        """
    )
    # verify()'s "empty tables" check scans every table in TABLES (all 28), since on a
    # real ingest a 0-row table means a CSV name is wrong. The scenario above only
    # exercises the tables involved in the Pikachu/type-matchup checks, so stub a
    # placeholder row into every other table to make this fixture a genuinely
    # "healthy" (fully populated) database rather than a partial one.
    seeded_tables = {
        "pokemon",
        "pokemon_species",
        "pokemon_species_names",
        "types",
        "type_names",
        "pokemon_types",
        "type_efficacy",
        "pokemon_stats",
    }
    for table in TABLES:
        if table in seeded_tables:
            continue
        column_count = len(conn.execute(f"PRAGMA table_info({table})").fetchall())
        placeholders = ",".join("?" for _ in range(column_count))
        conn.execute(f"INSERT INTO {table} VALUES ({placeholders})", [None] * column_count)
    conn.commit()
    apply_views(conn)
    conn.close()


def test_verify_passes_on_healthy_database(tmp_path):
    db = tmp_path / "pokedex.db"
    _seed(db)
    assert verify(db) == []


def test_verify_reports_wrong_pikachu_speed(tmp_path):
    db = tmp_path / "pokedex.db"
    _seed(db, speed=60)
    failures = verify(db)
    assert any("speed" in f for f in failures)


def test_verify_reports_wrong_type_effectiveness(tmp_path):
    db = tmp_path / "pokedex.db"
    _seed(db, factor=100)
    failures = verify(db)
    assert any("Water" in f for f in failures)
