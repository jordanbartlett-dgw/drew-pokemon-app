from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from pydantic_ai import models

from api.db import open_read_only
from ingest.schema import apply_schema
from ingest.views import apply_views

models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


_SEED = """
INSERT INTO pokemon VALUES (25,'pikachu',25,4,60,112,32,1);
INSERT INTO pokemon VALUES (26,'raichu',26,8,300,218,35,1);
INSERT INTO pokemon VALUES (6,'charizard',6,17,905,267,7,1);
INSERT INTO pokemon VALUES (7,'squirtle',7,5,90,63,10,1);
INSERT INTO pokemon_species
    (id,identifier,generation_id,evolves_from_species_id,evolution_chain_id,is_legendary,is_mythical)
    VALUES (25,'pikachu',1,NULL,10,0,0),
           (26,'raichu',1,25,10,0,0),
           (6,'charizard',1,5,2,0,0),
           (7,'squirtle',1,NULL,3,0,0);
INSERT INTO pokemon_species_names VALUES
    (25,9,'Pikachu','Mouse Pokémon'),
    (26,9,'Raichu','Mouse Pokémon'),
    (6,9,'Charizard','Flame Pokémon'),
    (7,9,'Squirtle','Tiny Turtle Pokémon');
INSERT INTO pokemon_species_flavor_text
    VALUES (25,40,9,'It raises its tail to check its surroundings.');
INSERT INTO types VALUES
    (13,'electric',1,3),(10,'fire',1,3),(3,'flying',1,2),(11,'water',1,3),(5,'ground',1,2);
INSERT INTO type_names VALUES
    (13,9,'Electric'),(10,9,'Fire'),(3,9,'Flying'),(11,9,'Water'),(5,9,'Ground');
INSERT INTO pokemon_types VALUES (25,13,1),(26,13,1),(6,10,1),(6,3,2),(7,11,1);
INSERT INTO type_efficacy VALUES
    (11,10,200),(10,11,50),(5,13,200),(13,5,0),(13,11,200),(13,3,200),(11,3,100);
INSERT INTO pokemon_stats VALUES
    (25,1,35,0),(25,2,55,0),(25,3,40,0),(25,4,50,0),(25,5,50,0),(25,6,90,0),
    (26,1,60,0),(26,2,90,0),(26,3,55,0),(26,4,90,0),(26,5,80,0),(26,6,110,0),
    (6,1,78,0),(6,2,84,0),(6,3,78,0),(6,4,109,0),(6,5,85,0),(6,6,100,0),
    (7,1,44,0),(7,2,48,0),(7,3,65,0),(7,4,50,0),(7,5,64,0),(7,6,43,0);
INSERT INTO abilities VALUES (9,'static',3,1),(66,'blaze',3,1),(67,'torrent',3,1);
INSERT INTO ability_names VALUES (9,9,'Static'),(66,9,'Blaze'),(67,9,'Torrent');
INSERT INTO pokemon_abilities VALUES (25,9,0,1),(26,9,0,1),(6,66,0,1),(7,67,0,1);
INSERT INTO evolution_triggers VALUES (1,'level-up'),(3,'use-item');
INSERT INTO pokemon_evolution (id,evolved_species_id,evolution_trigger_id,minimum_level)
    VALUES (1,26,3,NULL),(2,6,1,36);
"""


@pytest.fixture
def pokedex_path(tmp_path) -> Path:
    path = tmp_path / "pokedex.db"
    conn = sqlite3.connect(path)
    apply_schema(conn)
    conn.executescript(_SEED)
    conn.commit()
    apply_views(conn)
    conn.close()
    return path


@pytest.fixture
def pokedex(pokedex_path):
    return open_read_only(pokedex_path)
