from __future__ import annotations

import pytest

from api.sql_guard import MAX_ROWS, UnsafeSqlError, validate_sql


def test_adds_limit_when_missing():
    assert (
        validate_sql("SELECT name FROM v_pokemon") == f"SELECT name FROM v_pokemon LIMIT {MAX_ROWS}"
    )


def test_keeps_small_limit():
    assert (
        validate_sql("SELECT name FROM v_pokemon LIMIT 5") == "SELECT name FROM v_pokemon LIMIT 5"
    )


def test_caps_oversized_limit():
    assert validate_sql("SELECT name FROM v_pokemon LIMIT 5000").endswith(f"LIMIT {MAX_ROWS}")


def test_strips_trailing_semicolon():
    assert validate_sql("SELECT 1;") == f"SELECT 1 LIMIT {MAX_ROWS}"


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE pokemon",
        "DELETE FROM pokemon",
        "UPDATE pokemon SET id = 1",
        "INSERT INTO pokemon VALUES (1)",
        "ATTACH DATABASE 'x.db' AS x",
        "PRAGMA table_info(pokemon)",
        "CREATE TABLE x (a INT)",
        "SELECT 1; DROP TABLE pokemon",
        "WITH x AS (SELECT 1) DELETE FROM pokemon",
        "",
        "   ",
    ],
)
def test_rejects_unsafe_sql(sql):
    with pytest.raises(UnsafeSqlError):
        validate_sql(sql)


def test_allows_leading_cte():
    out = validate_sql(
        "WITH fast AS (SELECT * FROM v_pokemon WHERE speed > 100) SELECT name FROM fast"
    )
    assert out.endswith(f"LIMIT {MAX_ROWS}")


def test_caps_oversized_limit_with_offset():
    out = validate_sql("SELECT name FROM v_pokemon LIMIT 5000 OFFSET 10")
    assert out == f"SELECT name FROM v_pokemon LIMIT {MAX_ROWS} OFFSET 10"


def test_keeps_small_limit_with_offset():
    out = validate_sql("SELECT name FROM v_pokemon LIMIT 5 OFFSET 10")
    assert out == "SELECT name FROM v_pokemon LIMIT 5 OFFSET 10"


def test_keyword_in_string_literal_is_not_forbidden():
    out = validate_sql("SELECT name FROM v_pokemon WHERE name = 'Porygon-Z'")
    assert out == f"SELECT name FROM v_pokemon WHERE name = 'Porygon-Z' LIMIT {MAX_ROWS}"


def test_semicolon_in_string_literal_is_allowed():
    out = validate_sql("SELECT ';' AS x")
    assert out == f"SELECT ';' AS x LIMIT {MAX_ROWS}"


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1 -- DROP TABLE pokemon",
        "SELECT /* ATTACH */ 1",
        "-- comment\nSELECT 1",
        "SELECT 1\n-- \nDROP TABLE pokemon",
    ],
)
def test_rejects_comments(sql):
    with pytest.raises(UnsafeSqlError):
        validate_sql(sql)


def test_rejects_case_and_whitespace_variations():
    with pytest.raises(UnsafeSqlError):
        validate_sql("AtTaCh DATABASE 'x.db' AS x")
    with pytest.raises(UnsafeSqlError):
        validate_sql("ATTACH\tDATABASE 'x.db' AS x")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM v_pokemon LIMIT 0,10",
        "SELECT 1 LIMIT -1",
        "SELECT 1 LIMIT 5+5",
    ],
)
def test_rejects_non_integer_limit_forms(sql):
    with pytest.raises(UnsafeSqlError, match="plain whole number"):
        validate_sql(sql)


def test_nested_limit_without_outer_limit_gets_outer_limit_appended():
    out = validate_sql("SELECT * FROM (SELECT * FROM v_pokemon LIMIT 5) AS t")
    assert out == f"SELECT * FROM (SELECT * FROM v_pokemon LIMIT 5) AS t LIMIT {MAX_ROWS}"


@pytest.mark.parametrize(
    "sql",
    [
        "(SELECT * FROM v_pokemon LIMIT 5000)",
        "((SELECT * FROM v_pokemon))",
        "(SELECT id FROM v_pokemon) UNION (SELECT id FROM v_pokemon)",
        "(WITH x AS (SELECT 1) SELECT * FROM x)",
        "   (SELECT 1)",
    ],
)
def test_rejects_leading_parenthesis(sql):
    with pytest.raises(UnsafeSqlError, match="parentheses"):
        validate_sql(sql)


def test_allows_unwrapped_union():
    out = validate_sql("SELECT id FROM v_pokemon UNION SELECT id FROM v_pokemon")
    assert out.endswith(f"LIMIT {MAX_ROWS}")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM (SELECT * FROM v_pokemon) AS t",
        "SELECT id, (SELECT COUNT(*) FROM v_pokemon) AS c FROM v_pokemon",
        "SELECT * FROM v_pokemon WHERE id IN (SELECT id FROM v_pokemon)",
        "WITH fast AS (SELECT * FROM v_pokemon WHERE speed > 100) SELECT id FROM fast",
    ],
)
def test_allows_legitimate_non_leading_parens(sql):
    out = validate_sql(sql)
    assert out.endswith(f"LIMIT {MAX_ROWS}")
