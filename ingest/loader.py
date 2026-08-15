from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

ENGLISH_LANGUAGE_ID = 9

_LANGUAGE_COLUMNS = ("local_language_id", "language_id")
_FLAVOR_COLUMNS = {"flavor_text"}


def clean_flavor_text(raw: str) -> str:
    """PokeAPI embeds form feeds and hard newlines mid-sentence. Collapse them."""
    return " ".join(raw.replace("\f", " ").replace("\n", " ").split())


def load_table(
    conn: sqlite3.Connection,
    table: str,
    csv_path: Path,
    english_only: bool = False,
) -> int:
    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        source_columns = reader.fieldnames or []
        target_columns = ["order_" if c == "order" else c for c in source_columns]

        language_column = next((c for c in _LANGUAGE_COLUMNS if c in source_columns), None)

        placeholders = ",".join("?" for _ in target_columns)
        sql = f"INSERT INTO {table} ({','.join(target_columns)}) VALUES ({placeholders})"

        rows: list[tuple[object, ...]] = []
        for record in reader:
            if english_only and language_column is not None:
                if record[language_column] != str(ENGLISH_LANGUAGE_ID):
                    continue
            values: list[object] = []
            for column in source_columns:
                value = record[column]
                if value == "":
                    values.append(None)
                elif column in _FLAVOR_COLUMNS:
                    values.append(clean_flavor_text(value))
                else:
                    values.append(value)
            rows.append(tuple(values))

    conn.executemany(sql, rows)
    conn.commit()
    return len(rows)
