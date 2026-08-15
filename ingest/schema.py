from __future__ import annotations

import sqlite3

TABLES: dict[str, str] = {
    "pokemon": """
        CREATE TABLE pokemon (
            id INTEGER PRIMARY KEY, identifier TEXT, species_id INTEGER,
            height INTEGER, weight INTEGER, base_experience INTEGER,
            order_ INTEGER, is_default INTEGER
        )""",
    "pokemon_species": """
        CREATE TABLE pokemon_species (
            id INTEGER PRIMARY KEY, identifier TEXT, generation_id INTEGER,
            evolves_from_species_id INTEGER, evolution_chain_id INTEGER,
            color_id INTEGER, shape_id INTEGER, habitat_id INTEGER,
            gender_rate INTEGER, capture_rate INTEGER, base_happiness INTEGER,
            is_baby INTEGER, hatch_counter INTEGER, has_gender_differences INTEGER,
            growth_rate_id INTEGER, forms_switchable INTEGER, is_legendary INTEGER,
            is_mythical INTEGER, order_ INTEGER, conquest_order INTEGER
        )""",
    "pokemon_forms": """
        CREATE TABLE pokemon_forms (
            id INTEGER PRIMARY KEY, identifier TEXT, form_identifier TEXT,
            pokemon_id INTEGER, introduced_in_version_group_id INTEGER,
            is_default INTEGER, is_battle_only INTEGER, is_mega INTEGER,
            form_order INTEGER, order_ INTEGER
        )""",
    "types": """
        CREATE TABLE types (
            id INTEGER PRIMARY KEY, identifier TEXT,
            generation_id INTEGER, damage_class_id INTEGER
        )""",
    "type_names": """
        CREATE TABLE type_names (type_id INTEGER, local_language_id INTEGER, name TEXT)""",
    "pokemon_types": """
        CREATE TABLE pokemon_types (pokemon_id INTEGER, type_id INTEGER, slot INTEGER)""",
    "type_efficacy": """
        CREATE TABLE type_efficacy (
            damage_type_id INTEGER, target_type_id INTEGER, damage_factor INTEGER
        )""",
    "abilities": """
        CREATE TABLE abilities (
            id INTEGER PRIMARY KEY, identifier TEXT,
            generation_id INTEGER, is_main_series INTEGER
        )""",
    "ability_names": """
        CREATE TABLE ability_names (ability_id INTEGER, local_language_id INTEGER, name TEXT)""",
    "ability_flavor_text": """
        CREATE TABLE ability_flavor_text (
            ability_id INTEGER, version_group_id INTEGER,
            language_id INTEGER, flavor_text TEXT
        )""",
    "pokemon_abilities": """
        CREATE TABLE pokemon_abilities (
            pokemon_id INTEGER, ability_id INTEGER, is_hidden INTEGER, slot INTEGER
        )""",
    "stats": """
        CREATE TABLE stats (
            id INTEGER PRIMARY KEY, damage_class_id INTEGER, identifier TEXT,
            is_battle_only INTEGER, game_index INTEGER
        )""",
    "stat_names": """
        CREATE TABLE stat_names (stat_id INTEGER, local_language_id INTEGER, name TEXT)""",
    "pokemon_stats": """
        CREATE TABLE pokemon_stats (
            pokemon_id INTEGER, stat_id INTEGER, base_stat INTEGER, effort INTEGER
        )""",
    "moves": """
        CREATE TABLE moves (
            id INTEGER PRIMARY KEY, identifier TEXT, generation_id INTEGER,
            type_id INTEGER, power INTEGER, pp INTEGER, accuracy INTEGER,
            priority INTEGER, target_id INTEGER, damage_class_id INTEGER,
            effect_id INTEGER, effect_chance INTEGER, contest_type_id INTEGER,
            contest_effect_id INTEGER, super_contest_effect_id INTEGER
        )""",
    "move_names": """
        CREATE TABLE move_names (move_id INTEGER, local_language_id INTEGER, name TEXT)""",
    "move_damage_classes": """
        CREATE TABLE move_damage_classes (id INTEGER PRIMARY KEY, identifier TEXT)""",
    "pokemon_moves": """
        CREATE TABLE pokemon_moves (
            pokemon_id INTEGER, version_group_id INTEGER, move_id INTEGER,
            pokemon_move_method_id INTEGER, level INTEGER, order_ INTEGER, mastery INTEGER
        )""",
    "pokemon_move_methods": """
        CREATE TABLE pokemon_move_methods (id INTEGER PRIMARY KEY, identifier TEXT)""",
    "evolution_chains": """
        CREATE TABLE evolution_chains (id INTEGER PRIMARY KEY, baby_trigger_item_id INTEGER)""",
    "evolution_triggers": """
        CREATE TABLE evolution_triggers (id INTEGER PRIMARY KEY, identifier TEXT)""",
    "pokemon_evolution": """
        CREATE TABLE pokemon_evolution (
            id INTEGER PRIMARY KEY, evolved_species_id INTEGER,
            evolution_trigger_id INTEGER, version_group_id INTEGER, is_default INTEGER,
            trigger_item_id INTEGER, minimum_level INTEGER, gender_id INTEGER,
            location_id INTEGER, held_item_id INTEGER, time_of_day TEXT,
            known_move_id INTEGER, known_move_type_id INTEGER, minimum_happiness INTEGER,
            minimum_beauty INTEGER, minimum_affection INTEGER,
            relative_physical_stats INTEGER, party_species_id INTEGER,
            party_type_id INTEGER, trade_species_id INTEGER,
            needs_overworld_rain INTEGER, turn_upside_down INTEGER,
            needs_multiplayer INTEGER, near_special_rock INTEGER, region_id INTEGER,
            base_form_id INTEGER, evolved_form_id INTEGER, used_move_id INTEGER,
            minimum_move_count INTEGER, minimum_steps INTEGER, minimum_damage_taken INTEGER
        )""",
    "generations": """
        CREATE TABLE generations (
            id INTEGER PRIMARY KEY, main_region_id INTEGER, identifier TEXT
        )""",
    "generation_names": """
        CREATE TABLE generation_names (
            generation_id INTEGER, local_language_id INTEGER, name TEXT
        )""",
    "pokemon_species_names": """
        CREATE TABLE pokemon_species_names (
            pokemon_species_id INTEGER, local_language_id INTEGER, name TEXT, genus TEXT
        )""",
    "pokemon_species_flavor_text": """
        CREATE TABLE pokemon_species_flavor_text (
            species_id INTEGER, version_id INTEGER, language_id INTEGER, flavor_text TEXT
        )""",
    "version_groups": """
        CREATE TABLE version_groups (
            id INTEGER PRIMARY KEY, identifier TEXT, generation_id INTEGER, order_ INTEGER
        )""",
    "languages": """
        CREATE TABLE languages (
            id INTEGER PRIMARY KEY, iso639 TEXT, iso3166 TEXT,
            identifier TEXT, official INTEGER, order_ INTEGER
        )""",
}

INDEXES: list[str] = [
    "CREATE INDEX idx_pokemon_species ON pokemon(species_id)",
    "CREATE INDEX idx_pokemon_types_pokemon ON pokemon_types(pokemon_id)",
    "CREATE INDEX idx_pokemon_stats_pokemon ON pokemon_stats(pokemon_id)",
    "CREATE INDEX idx_pokemon_abilities_pokemon ON pokemon_abilities(pokemon_id)",
    "CREATE INDEX idx_pokemon_moves_pokemon ON pokemon_moves(pokemon_id)",
    "CREATE INDEX idx_species_chain ON pokemon_species(evolution_chain_id)",
    "CREATE INDEX idx_efficacy ON type_efficacy(damage_type_id, target_type_id)",
]


def apply_schema(conn: sqlite3.Connection) -> None:
    for ddl in TABLES.values():
        conn.execute(ddl)
    conn.commit()


def apply_indexes(conn: sqlite3.Connection) -> None:
    for ddl in INDEXES:
        conn.execute(ddl)
    conn.commit()
