from __future__ import annotations

import difflib
import sqlite3
from typing import Any

from api.db import query
from api.models import BaseStats, FindPokemonResult, PokemonProfile

IMAGE_URL_PREFIX = "/images/"


def _abilities(conn: sqlite3.Connection, pokemon_id: int) -> list[str]:
    rows = query(
        conn,
        """
        SELECT an.name AS name
        FROM pokemon_abilities pa
        JOIN ability_names an ON an.ability_id = pa.ability_id AND an.local_language_id = 9
        WHERE pa.pokemon_id = ?
        ORDER BY pa.slot
        """,
        (pokemon_id,),
    )
    return [row["name"] for row in rows]


def _profile(conn: sqlite3.Connection, row: dict[str, Any]) -> PokemonProfile:
    types = [t for t in (row["type1"], row["type2"]) if t]
    return PokemonProfile(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        generation=row["generation"],
        types=types,
        stats=BaseStats(
            hp=row["hp"],
            attack=row["attack"],
            defense=row["defense"],
            special_attack=row["special_attack"],
            special_defense=row["special_defense"],
            speed=row["speed"],
        ),
        height_m=row["height_m"],
        weight_kg=row["weight_kg"],
        abilities=_abilities(conn, row["id"]),
        artwork_url=f"{IMAGE_URL_PREFIX}{row['artwork_path']}",
        sprite_url=f"{IMAGE_URL_PREFIX}{row['sprite_path']}",
        genus=row["genus"],
        flavor_text=row["flavor_text"],
        is_legendary=bool(row["is_legendary"]),
        is_mythical=bool(row["is_mythical"]),
    )


def load_profile(conn: sqlite3.Connection, pokemon_id: int) -> PokemonProfile | None:
    rows = query(conn, "SELECT * FROM v_pokemon WHERE id = ?", (pokemon_id,))
    return _profile(conn, rows[0]) if rows else None


def find_pokemon(conn: sqlite3.Connection, name_or_id: str) -> FindPokemonResult:
    """Resolve a name, nickname-ish spelling, or number to one Pokémon."""
    needle = name_or_id.strip().lower().replace(" ", "-")

    rows = query(conn, "SELECT * FROM v_pokemon WHERE slug = ?", (needle,))
    if not rows:
        rows = query(conn, "SELECT * FROM v_pokemon WHERE LOWER(name) = ?", (needle,))
    if not rows and needle.isdigit():
        rows = query(conn, "SELECT * FROM v_pokemon WHERE id = ?", (int(needle),))
    if rows:
        return FindPokemonResult(pokemon=_profile(conn, rows[0]))

    slugs = [row["slug"] for row in query(conn, "SELECT slug FROM v_pokemon")]
    candidates = difflib.get_close_matches(needle, slugs, n=5, cutoff=0.7)
    return FindPokemonResult(pokemon=None, candidates=candidates)
