from __future__ import annotations

import argparse
import sqlite3
import tempfile
from pathlib import Path

from ingest.images import SPRITE_PATHS, download_images
from ingest.loader import load_table
from ingest.schema import TABLES, apply_indexes, apply_schema
from ingest.source import (
    CSV_PATH_IN_REPO,
    CSV_REPO,
    SPRITES_REPO,
    sparse_clone,
)
from ingest.views import apply_views

ENGLISH_TABLES = {
    "type_names",
    "ability_names",
    "ability_flavor_text",
    "stat_names",
    "move_names",
    "generation_names",
    "pokemon_species_names",
    "pokemon_species_flavor_text",
}


def build_database(csv_dir: Path, db_path: Path) -> dict[str, int]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()

    conn = sqlite3.connect(db_path)
    apply_schema(conn)

    counts: dict[str, int] = {}
    for table in TABLES:
        counts[table] = load_table(
            conn,
            table,
            csv_dir / f"{table}.csv",
            english_only=table in ENGLISH_TABLES,
        )

    apply_indexes(conn)
    apply_views(conn)
    conn.close()
    return counts


def verify(db_path: Path) -> list[str]:
    """Return a list of failed checks. Empty means the database is trustworthy."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    failures: list[str] = []

    row = conn.execute("SELECT * FROM v_pokemon WHERE id = 25").fetchone()
    if row is None:
        failures.append("Pikachu (id 25) is missing from v_pokemon")
    else:
        if row["name"] != "Pikachu":
            failures.append(f"Pokemon 25 is named {row['name']!r}, expected 'Pikachu'")
        if row["type1"] != "Electric":
            failures.append(f"Pikachu type1 is {row['type1']!r}, expected 'Electric'")
        if row["speed"] != 90:
            failures.append(f"Pikachu base speed is {row['speed']}, expected 90")
        if row["weight_kg"] != 6.0:
            failures.append(f"Pikachu weight is {row['weight_kg']}, expected 6.0")

    matchup = conn.execute(
        "SELECT multiplier FROM v_type_matchup WHERE attacking = 'Water' AND defending = 'Fire'"
    ).fetchone()
    if matchup is None or matchup["multiplier"] != 2.0:
        failures.append("Water attacking Fire is not 2.0x")

    empty = [t for t in TABLES if conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0]
    if empty:
        failures.append(f"Empty tables: {', '.join(sorted(empty))}")

    eevee_evolutions = conn.execute(
        "SELECT COUNT(*) FROM v_evolution WHERE from_name = 'Eevee'"
    ).fetchone()[0]
    if eevee_evolutions != 8:
        failures.append(f"Eevee's evolution chain has {eevee_evolutions} rows, expected 8")

    duplicate_evolutions = conn.execute(
        """
        SELECT chain_id, from_name, to_name, COUNT(*) AS n
        FROM v_evolution
        GROUP BY chain_id, from_name, to_name
        HAVING COUNT(*) > 1
        """
    ).fetchall()
    if duplicate_evolutions:
        pairs = ", ".join(
            f"{r['from_name']}->{r['to_name']} (x{r['n']})" for r in duplicate_evolutions
        )
        failures.append(f"v_evolution has duplicate evolution rows: {pairs}")

    conn.close()
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the Drew's Pokémon App database.")
    parser.add_argument("--db", type=Path, default=Path("data/pokedex.db"))
    parser.add_argument("--images-dir", type=Path, default=Path("data/images"))
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "pokeapi-cache")
    parser.add_argument("--skip-images", action="store_true")
    args = parser.parse_args()

    print("Cloning PokeAPI CSV data...")
    csv_checkout = sparse_clone(CSV_REPO, [CSV_PATH_IN_REPO], args.cache / "pokeapi")

    print("Building the database...")
    counts = build_database(csv_checkout / CSV_PATH_IN_REPO, args.db)
    for table, count in counts.items():
        print(f"  {table:<32} {count:>7,} rows")

    if args.skip_images:
        print("Skipping images.")
    else:
        print("Cloning sprites (this is the slow part, several minutes)...")
        sprite_checkout = sparse_clone(SPRITES_REPO, SPRITE_PATHS, args.cache / "sprites")
        images = download_images(sprite_checkout, args.images_dir)
        print(f"  {images.copied:,} copied, {images.skipped:,} already present")

    failures = verify(args.db)
    if failures:
        print("\nVERIFICATION FAILED:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nVerification passed. Drew's Pokédex is ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
