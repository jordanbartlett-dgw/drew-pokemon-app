from __future__ import annotations

import difflib
import sqlite3
from typing import Any

from api.db import query
from api.models import (
    BaseStats,
    Comparison,
    EvolutionChain,
    EvolutionStep,
    FindPokemonResult,
    MatchupReport,
    PokemonProfile,
    SqlResult,
    TypeMatchup,
)
from api.sql_guard import MAX_ROWS, validate_sql

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


def _known_types(conn: sqlite3.Connection) -> dict[str, str]:
    rows = query(conn, "SELECT DISTINCT attacking AS name FROM v_type_matchup")
    rows += query(conn, "SELECT DISTINCT defending AS name FROM v_type_matchup")
    return {row["name"].lower(): row["name"] for row in rows}


def type_matchup(conn: sqlite3.Connection, attacking: str, defending: str) -> MatchupReport:
    """How much damage `attacking` does to `defending`. Dual types use 'Water/Flying'."""
    known = _known_types(conn)

    def resolve(name: str) -> str:
        key = name.strip().lower()
        if key not in known:
            raise ValueError(
                f"{name} is not a Pokémon type. Known types: {', '.join(sorted(known.values()))}"
            )
        return known[key]

    attack_type = resolve(attacking)
    defend_types = [resolve(part) for part in defending.split("/") if part.strip()]

    matchups: list[TypeMatchup] = []
    combined = 1.0
    for defend_type in defend_types:
        rows = query(
            conn,
            "SELECT multiplier FROM v_type_matchup WHERE attacking = ? AND defending = ?",
            (attack_type, defend_type),
        )
        multiplier = rows[0]["multiplier"] if rows else 1.0
        matchups.append(
            TypeMatchup(attacking=attack_type, defending=defend_type, multiplier=multiplier)
        )
        combined *= multiplier

    return MatchupReport(
        attacking_types=[attack_type],
        defending_types=defend_types,
        matchups=matchups,
        combined_multiplier=combined,
    )


def compare(conn: sqlite3.Connection, names: list[str]) -> Comparison:
    """Side-by-side profiles. Names that do not resolve are dropped."""
    profiles = [
        result.pokemon
        for result in (find_pokemon(conn, name) for name in names)
        if result.pokemon is not None
    ]
    if not profiles:
        return Comparison(pokemon=[], fastest="", highest_total="")

    fastest = max(profiles, key=lambda p: p.stats.speed)
    strongest = max(profiles, key=lambda p: p.stats.total)
    return Comparison(pokemon=profiles, fastest=fastest.name, highest_total=strongest.name)


def evolution_chain(conn: sqlite3.Connection, name: str) -> EvolutionChain | None:
    """Every step in the evolution line the named Pokémon belongs to."""
    found = find_pokemon(conn, name)
    if found.pokemon is None:
        return None

    chain_rows = query(
        conn,
        "SELECT evolution_chain_id AS chain_id FROM pokemon_species WHERE id = ?",
        (found.pokemon.id,),
    )
    if not chain_rows or chain_rows[0]["chain_id"] is None:
        return None
    chain_id = chain_rows[0]["chain_id"]

    steps = query(
        conn,
        "SELECT from_name, to_name, trigger, min_level FROM v_evolution WHERE chain_id = ?",
        (chain_id,),
    )
    return EvolutionChain(
        chain_id=chain_id,
        steps=[EvolutionStep(**step) for step in steps],
    )


def run_sql(conn: sqlite3.Connection, sql: str) -> SqlResult:
    """Run a read-only SELECT against the Pokédex. Raises UnsafeSqlError if rejected."""
    safe_sql = validate_sql(sql)
    rows = query(conn, safe_sql)
    columns = list(rows[0].keys()) if rows else []
    return SqlResult(
        sql=safe_sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=len(rows) >= MAX_ROWS,
    )
