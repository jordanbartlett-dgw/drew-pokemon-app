from __future__ import annotations

import pytest

from api.sql_guard import UnsafeSqlError
from api.tools import compare, evolution_chain, run_sql, type_matchup


def test_single_type_matchup(pokedex):
    report = type_matchup(pokedex, "Water", "Fire")
    assert report.combined_multiplier == 2.0
    assert report.matchups[0].label == "super effective"


def test_dual_type_matchup_multiplies(pokedex):
    report = type_matchup(pokedex, "Electric", "Water/Flying")
    assert report.defending_types == ["Water", "Flying"]
    assert report.combined_multiplier == 4.0


def test_immunity_wins(pokedex):
    assert type_matchup(pokedex, "Electric", "Ground").combined_multiplier == 0.0


def test_missing_efficacy_row_defaults_to_neutral(pokedex):
    assert type_matchup(pokedex, "Fire", "Flying").combined_multiplier == 1.0


def test_unknown_type_is_reported(pokedex):
    with pytest.raises(ValueError, match="Sparkle"):
        type_matchup(pokedex, "Sparkle", "Fire")


def test_compare_picks_fastest_and_strongest(pokedex):
    result = compare(pokedex, ["pikachu", "charizard"])
    assert [p.name for p in result.pokemon] == ["Pikachu", "Charizard"]
    assert result.fastest == "Charizard"
    assert result.highest_total == "Charizard"


def test_compare_skips_unknown_names(pokedex):
    result = compare(pokedex, ["pikachu", "notapokemon"])
    assert [p.name for p in result.pokemon] == ["Pikachu"]


def test_evolution_chain_walks_the_line(pokedex):
    chain = evolution_chain(pokedex, "pikachu")
    assert chain is not None
    assert chain.chain_id == 10
    assert chain.steps[0].from_name == "Pikachu"
    assert chain.steps[0].to_name == "Raichu"
    assert chain.steps[0].trigger == "use-item"


def test_evolution_chain_returns_none_for_unknown(pokedex):
    assert evolution_chain(pokedex, "notapokemon") is None


def test_run_sql_returns_rows(pokedex):
    result = run_sql(pokedex, "SELECT name FROM v_pokemon WHERE type1 = 'Electric' ORDER BY id")
    assert result.columns == ["name"]
    assert [r["name"] for r in result.rows] == ["Pikachu", "Raichu"]
    assert result.row_count == 2
    assert result.truncated is False
    assert "LIMIT 200" in result.sql


def test_run_sql_rejects_writes(pokedex):
    with pytest.raises(UnsafeSqlError):
        run_sql(pokedex, "DROP TABLE pokemon")


def test_run_sql_marks_truncation(pokedex, monkeypatch):
    monkeypatch.setattr("api.tools.MAX_ROWS", 1)
    result = run_sql(pokedex, "SELECT name FROM v_pokemon LIMIT 1")
    assert result.truncated is True
