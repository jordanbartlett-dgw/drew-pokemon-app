from __future__ import annotations

import sqlite3

import pytest

from ingest.schema import apply_schema
from ingest.views import apply_views


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    apply_schema(c)
    c.executescript(
        """
        INSERT INTO pokemon VALUES (25,'pikachu',25,4,60,112,32,1);
        INSERT INTO pokemon VALUES (26,'raichu',26,8,300,218,35,1);
        INSERT INTO pokemon_species
            (id,identifier,generation_id,evolves_from_species_id,
             evolution_chain_id,is_legendary,is_mythical)
            VALUES (25,'pikachu',1,172,10,0,0);
        INSERT INTO pokemon_species
            (id,identifier,generation_id,evolves_from_species_id,
             evolution_chain_id,is_legendary,is_mythical)
            VALUES (26,'raichu',1,25,10,0,0);
        INSERT INTO pokemon_species_names VALUES (25,9,'Pikachu','Mouse Pokémon');
        INSERT INTO pokemon_species_names VALUES (26,9,'Raichu','Mouse Pokémon');
        INSERT INTO pokemon_species_flavor_text VALUES (25,1,9,'Old entry.');
        INSERT INTO pokemon_species_flavor_text VALUES (25,40,9,'Newest entry.');
        INSERT INTO types VALUES (13,'electric',1,3);
        INSERT INTO types VALUES (5,'ground',1,2);
        INSERT INTO type_names VALUES (13,9,'Electric');
        INSERT INTO type_names VALUES (5,9,'Ground');
        INSERT INTO pokemon_types VALUES (25,13,1);
        INSERT INTO pokemon_types VALUES (26,13,1);
        INSERT INTO type_efficacy VALUES (5,13,200);
        INSERT INTO type_efficacy VALUES (13,5,0);
        INSERT INTO pokemon_stats VALUES
            (25,1,35,0),(25,2,55,0),(25,3,40,0),(25,4,50,0),(25,5,50,0),(25,6,90,0);
        INSERT INTO pokemon_stats VALUES
            (26,1,60,0),(26,2,90,0),(26,3,55,0),(26,4,90,0),(26,5,80,0),(26,6,110,0);
        INSERT INTO evolution_triggers VALUES (3,'use-item');
        INSERT INTO pokemon_evolution
            (id,evolved_species_id,evolution_trigger_id,minimum_level) VALUES (1,26,3,NULL);
        INSERT INTO pokemon VALUES (6,'charizard',6,17,905,240,8,1);
        INSERT INTO pokemon_species
            (id,identifier,generation_id,evolves_from_species_id,
             evolution_chain_id,is_legendary,is_mythical)
            VALUES (6,'charizard',1,5,2,0,0);
        INSERT INTO types VALUES (10,'fire',1,3);
        INSERT INTO types VALUES (3,'flying',1,2);
        INSERT INTO type_names VALUES (10,9,'Fire');
        INSERT INTO type_names VALUES (3,9,'Flying');
        INSERT INTO pokemon_types VALUES (6,10,1);
        INSERT INTO pokemon_types VALUES (6,3,2);
        INSERT INTO moves
            (id,identifier,type_id,power,accuracy) VALUES (85,'thunderbolt',13,90,100);
        INSERT INTO move_names VALUES (85,9,'Thunderbolt');
        INSERT INTO pokemon_move_methods VALUES (1,'level-up');
        INSERT INTO pokemon_moves
            (pokemon_id,version_group_id,move_id,pokemon_move_method_id,level)
            VALUES (25,1,85,1,26);
        INSERT INTO pokemon_moves
            (pokemon_id,version_group_id,move_id,pokemon_move_method_id,level)
            VALUES (25,2,85,1,26);
        """
    )
    c.commit()
    apply_views(c)
    return c


def test_v_pokemon_shape(conn):
    row = conn.execute("SELECT * FROM v_pokemon WHERE id = 25").fetchone()
    assert row["name"] == "Pikachu"
    assert row["slug"] == "pikachu"
    assert row["type1"] == "Electric"
    assert row["type2"] is None
    assert row["speed"] == 90
    assert row["total_stats"] == 320
    assert row["height_m"] == 0.4
    assert row["weight_kg"] == 6.0
    assert row["generation"] == 1
    assert row["artwork_path"] == "official-artwork/25.png"
    assert row["sprite_path"] == "front-default/25.png"


def test_v_pokemon_uses_newest_flavor_text(conn):
    assert (
        conn.execute("SELECT flavor_text FROM v_pokemon WHERE id = 25").fetchone()[0]
        == "Newest entry."
    )


def test_v_type_matchup_multipliers(conn):
    rows = {
        (r["attacking"], r["defending"]): r["multiplier"]
        for r in conn.execute("SELECT * FROM v_type_matchup")
    }
    assert rows[("Ground", "Electric")] == 2.0
    assert rows[("Electric", "Ground")] == 0.0


def test_v_evolution_links_species(conn):
    row = conn.execute("SELECT * FROM v_evolution").fetchone()
    assert row["from_name"] == "Pikachu"
    assert row["to_name"] == "Raichu"
    assert row["trigger"] == "use-item"
    assert row["chain_id"] == 10


def test_v_pokemon_second_type(conn):
    row = conn.execute("SELECT * FROM v_pokemon WHERE id = 6").fetchone()
    assert row["type1"] == "Fire"
    assert row["type2"] == "Flying"


def test_v_pokemon_moves_returns_distinct_rows(conn):
    rows = conn.execute(
        "SELECT * FROM v_pokemon_moves WHERE pokemon = 'Pikachu' AND move = 'Thunderbolt'"
    ).fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row["method"] == "level-up"
    assert row["level"] == 26
    assert row["move_type"] == "Electric"
    assert row["power"] == 90
    assert row["accuracy"] == 100
