from __future__ import annotations

import sqlite3

import pytest

from ingest.loader import clean_flavor_text, load_table
from ingest.schema import apply_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    apply_schema(c)
    return c


def write(tmp_path, name, text):
    p = tmp_path / f"{name}.csv"
    p.write_text(text)
    return p


def test_load_table_inserts_rows(conn, tmp_path):
    csv = write(
        tmp_path,
        "types",
        "id,identifier,generation_id,damage_class_id\n10,fire,1,3\n11,water,1,3\n",
    )
    assert load_table(conn, "types", csv) == 2
    assert [r["identifier"] for r in conn.execute("SELECT identifier FROM types ORDER BY id")] == [
        "fire",
        "water",
    ]


def test_load_table_renames_order_column(conn, tmp_path):
    csv = write(
        tmp_path,
        "pokemon",
        "id,identifier,species_id,height,weight,base_experience,order,is_default\n25,pikachu,25,4,60,112,32,1\n",
    )
    load_table(conn, "pokemon", csv)
    row = conn.execute("SELECT * FROM pokemon").fetchone()
    assert row["order_"] == 32
    assert row["identifier"] == "pikachu"


def test_load_table_converts_empty_string_to_null(conn, tmp_path):
    csv = write(
        tmp_path,
        "moves",
        "id,identifier,generation_id,type_id,power,pp,accuracy,priority,target_id,damage_class_id,effect_id,effect_chance,contest_type_id,contest_effect_id,super_contest_effect_id\n1,pound,1,1,40,35,100,0,10,2,1,,5,1,5\n",
    )
    load_table(conn, "moves", csv)
    assert conn.execute("SELECT effect_chance FROM moves").fetchone()[0] is None


def test_load_table_english_only_filters_local_language_id(conn, tmp_path):
    csv = write(tmp_path, "type_names", "type_id,local_language_id,name\n10,9,Fire\n10,5,Feu\n")
    assert load_table(conn, "type_names", csv, english_only=True) == 1
    assert conn.execute("SELECT name FROM type_names").fetchone()[0] == "Fire"


def test_load_table_english_only_filters_language_id(conn, tmp_path):
    csv = write(
        tmp_path,
        "pokemon_species_flavor_text",
        "species_id,version_id,language_id,flavor_text\n25,1,9,Zap!\n25,1,5,Zap en francais\n",
    )
    assert load_table(conn, "pokemon_species_flavor_text", csv, english_only=True) == 1


def test_clean_flavor_text_strips_control_characters():
    assert clean_flavor_text("It keeps its\ftail\nraised.") == "It keeps its tail raised."
