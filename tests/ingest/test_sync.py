from __future__ import annotations

import sqlite3

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

import ingest.sync as sync
from api.store import create_conversation, ensure_schema, load_turns, open_store, save_turn
from ingest.schema import TABLES, apply_schema
from ingest.sync import verify
from ingest.views import apply_views


def _seed(db_path, speed: int = 90, factor: int = 200, eevee_evolutions: int = 8):
    """Seed a database with Pikachu/type data plus Eevee's evolution chain.

    `eevee_evolutions` controls how many of Eevee's 8 real evolutions are inserted,
    so tests can exercise verify()'s "wrong count" check by passing fewer than 8.
    """
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
        INSERT INTO evolution_triggers VALUES (3,'use-item');
        INSERT INTO pokemon_species
            (id,identifier,generation_id,evolves_from_species_id,evolution_chain_id)
            VALUES (133,'eevee',1,NULL,67);
        INSERT INTO pokemon_species_names VALUES (133,9,'Eevee','Evolution Pokémon');
        """
    )
    # Eevee's 8 real evolutions (species ids match PokeAPI's actual ids). Each is
    # inserted with is_default=1, mirroring the canonical row a real ingest keeps
    # after Fix 1 filters pokemon_evolution down from one row per game version.
    eeveelutions = [
        (134, "vaporeon"),
        (135, "jolteon"),
        (136, "flareon"),
        (196, "espeon"),
        (197, "umbreon"),
        (470, "leafeon"),
        (471, "glaceon"),
        (700, "sylveon"),
    ]
    for evolution_id, (species_id, identifier) in enumerate(
        eeveelutions[:eevee_evolutions], start=1
    ):
        conn.execute(
            "INSERT INTO pokemon_species "
            "(id,identifier,generation_id,evolves_from_species_id,evolution_chain_id) "
            "VALUES (?,?,1,133,67)",
            (species_id, identifier),
        )
        conn.execute(
            "INSERT INTO pokemon_species_names VALUES (?,9,?,'Evolution Pokémon')",
            (species_id, identifier.capitalize()),
        )
        conn.execute(
            "INSERT INTO pokemon_evolution "
            "(id,evolved_species_id,evolution_trigger_id,version_group_id,"
            "is_default,minimum_level) VALUES (?,?,3,1,1,NULL)",
            (evolution_id, species_id),
        )

    # verify()'s "empty tables" check scans every table in TABLES (all 28), since on a
    # real ingest a 0-row table means a CSV name is wrong. The scenario above only
    # exercises a subset of tables, so stub a placeholder row into every other table
    # to make this fixture a genuinely "healthy" (fully populated) database.
    seeded_tables = {
        "pokemon",
        "pokemon_species",
        "pokemon_species_names",
        "types",
        "type_names",
        "pokemon_types",
        "type_efficacy",
        "pokemon_stats",
        "evolution_triggers",
        "pokemon_evolution",
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


def test_verify_reports_wrong_eevee_evolution_count(tmp_path):
    db = tmp_path / "pokedex.db"
    _seed(db, eevee_evolutions=7)
    failures = verify(db)
    assert any("Eevee" in f and "7" in f for f in failures)


def test_verify_reports_duplicate_evolution_rows(tmp_path):
    db = tmp_path / "pokedex.db"
    _seed(db)
    conn = sqlite3.connect(db)
    # v_evolution's ROW_NUMBER() dedups by evolved_species_id, so it can't catch two
    # *different* child species that happen to render the same display name for the
    # same parent/chain (e.g. a names data error). That's the failure mode this
    # general (chain_id, from_name, to_name) check exists to catch.
    conn.execute(
        "INSERT INTO pokemon_species "
        "(id,identifier,generation_id,evolves_from_species_id,evolution_chain_id) "
        "VALUES (9999,'vaporeon-duplicate',1,133,67)"
    )
    conn.execute(
        "INSERT INTO pokemon_species_names VALUES (9999,9,'Vaporeon','Bubble Jet Pokémon')"
    )
    conn.execute(
        "INSERT INTO pokemon_evolution "
        "(id,evolved_species_id,evolution_trigger_id,version_group_id,"
        "is_default,minimum_level) VALUES (99,9999,3,1,1,NULL)"
    )
    conn.commit()
    conn.close()
    failures = verify(db)
    assert any("duplicate" in f.lower() for f in failures)


def _write_minimal_types_csv(csv_dir):
    csv_dir.mkdir(parents=True, exist_ok=True)
    (csv_dir / "types.csv").write_text("id,identifier,generation_id,damage_class_id\n10,fire,1,3\n")


def test_build_database_only_touches_db_path(tmp_path, monkeypatch):
    """Critical 2: `build_database` unlinks and rebuilds db_path (see the
    `db_path.unlink()` at the top of the function). Restricting the table list to
    one entry keeps this test fast -- it isn't exercising ingest's data correctness
    (that's verify(), tested above), only that build_database never reaches outside
    db_path onto any other file."""
    monkeypatch.setattr(sync, "TABLES", {"types": TABLES["types"]})
    csv_dir = tmp_path / "csv"
    _write_minimal_types_csv(csv_dir)

    db_path = tmp_path / "pokedex.db"
    other_path = tmp_path / "app.db"
    other_path.write_text("not a real sqlite file, just proof nothing touched it")

    sync.build_database(csv_dir, db_path)

    assert db_path.exists()
    assert other_path.read_text() == "not a real sqlite file, just proof nothing touched it"


def test_conversation_survives_a_rebuild_of_the_pokedex(tmp_path, monkeypatch):
    """Critical 2, end to end: a conversation saved in store_path (api/app.db) is
    completely unaffected by re-running the ingest against a separate db_path
    (api/pokedex.db) -- even when build_database deletes and recreates db_path."""
    monkeypatch.setattr(sync, "TABLES", {"types": TABLES["types"]})
    csv_dir = tmp_path / "csv"
    _write_minimal_types_csv(csv_dir)

    db_path = tmp_path / "pokedex.db"
    store_path = tmp_path / "app.db"

    store_conn = open_store(store_path)
    ensure_schema(store_conn)
    cid = create_conversation(store_conn, "Who is Pikachu?")
    save_turn(
        store_conn,
        cid,
        "Who is Pikachu?",
        "A mouse!",
        [],
        [
            ModelRequest(parts=[UserPromptPart(content="Who is Pikachu?")]),
            ModelResponse(parts=[TextPart(content="A mouse!")]),
        ],
    )

    # Build the Pokédex once, then rebuild it again -- simulating re-running the
    # ingest to refresh data. build_database unlinks and recreates db_path each time.
    sync.build_database(csv_dir, db_path)
    sync.build_database(csv_dir, db_path)

    turns = load_turns(store_conn, cid)
    assert len(turns) == 1
    assert turns[0].assistant_text == "A mouse!"
