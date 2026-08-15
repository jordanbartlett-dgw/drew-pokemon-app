from __future__ import annotations

from api.models import BaseStats, PokemonProfile, SqlResult, TypeMatchup


def test_base_stats_total():
    stats = BaseStats(hp=35, attack=55, defense=40, special_attack=50, special_defense=50, speed=90)
    assert stats.total == 320


def test_pokemon_profile_builds_image_urls():
    profile = PokemonProfile(
        id=25,
        name="Pikachu",
        slug="pikachu",
        generation=1,
        types=["Electric"],
        stats=BaseStats(
            hp=35, attack=55, defense=40, special_attack=50, special_defense=50, speed=90
        ),
        height_m=0.4,
        weight_kg=6.0,
        abilities=["Static"],
        artwork_url="/images/official-artwork/25.png",
        sprite_url="/images/front-default/25.png",
    )
    assert profile.artwork_url.startswith("/images/")
    assert profile.genus is None
    assert profile.is_legendary is False


def test_type_matchup_label_reads_plainly():
    assert (
        TypeMatchup(attacking="Water", defending="Fire", multiplier=2.0).label == "super effective"
    )
    assert (
        TypeMatchup(attacking="Fire", defending="Water", multiplier=0.5).label
        == "not very effective"
    )
    assert (
        TypeMatchup(attacking="Electric", defending="Ground", multiplier=0.0).label == "no effect"
    )
    assert (
        TypeMatchup(attacking="Normal", defending="Normal", multiplier=1.0).label == "normal damage"
    )


def test_sql_result_flags_truncation():
    result = SqlResult(sql="SELECT 1", columns=["a"], rows=[{"a": 1}], row_count=1, truncated=False)
    assert result.truncated is False
