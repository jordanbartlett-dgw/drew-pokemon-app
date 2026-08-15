from __future__ import annotations

from api.tools import find_pokemon


def test_finds_by_slug(pokedex):
    result = find_pokemon(pokedex, "pikachu")
    assert result.pokemon is not None
    assert result.pokemon.name == "Pikachu"
    assert result.pokemon.types == ["Electric"]
    assert result.pokemon.stats.speed == 90
    assert result.pokemon.stats.total == 320
    assert result.pokemon.abilities == ["Static"]
    assert result.pokemon.artwork_url == "/images/official-artwork/25.png"
    assert result.pokemon.weight_kg == 6.0
    assert result.candidates == []


def test_finds_case_insensitively(pokedex):
    assert find_pokemon(pokedex, "PIKACHU").pokemon.name == "Pikachu"


def test_finds_by_id(pokedex):
    assert find_pokemon(pokedex, "6").pokemon.name == "Charizard"


def test_returns_both_types_in_slot_order(pokedex):
    assert find_pokemon(pokedex, "charizard").pokemon.types == ["Fire", "Flying"]


def test_typo_returns_candidates_not_a_match(pokedex):
    result = find_pokemon(pokedex, "pikchu")
    assert result.pokemon is None
    assert "pikachu" in result.candidates


def test_nonsense_returns_no_candidates(pokedex):
    result = find_pokemon(pokedex, "zzzzzzzz")
    assert result.pokemon is None
    assert result.candidates == []
