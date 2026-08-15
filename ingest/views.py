from __future__ import annotations

import sqlite3

VIEWS: dict[str, str] = {
    "v_pokemon": """
        CREATE VIEW v_pokemon AS
        SELECT
            p.id                                  AS id,
            COALESCE(sn.name, p.identifier)       AS name,
            p.identifier                          AS slug,
            s.generation_id                       AS generation,
            t1.name                               AS type1,
            t2.name                               AS type2,
            st.hp, st.attack, st.defense,
            st.special_attack, st.special_defense, st.speed,
            st.hp + st.attack + st.defense
              + st.special_attack + st.special_defense + st.speed AS total_stats,
            ROUND(p.height / 10.0, 2)             AS height_m,
            ROUND(p.weight / 10.0, 2)             AS weight_kg,
            s.is_legendary                        AS is_legendary,
            s.is_mythical                         AS is_mythical,
            'official-artwork/' || p.id || '.png' AS artwork_path,
            'front-default/' || p.id || '.png'    AS sprite_path,
            sn.genus                              AS genus,
            ft.flavor_text                        AS flavor_text
        FROM pokemon p
        JOIN pokemon_species s ON s.id = p.species_id
        LEFT JOIN pokemon_species_names sn
               ON sn.pokemon_species_id = s.id AND sn.local_language_id = 9
        LEFT JOIN (
            SELECT pt.pokemon_id, tn.name
            FROM pokemon_types pt
            JOIN type_names tn ON tn.type_id = pt.type_id AND tn.local_language_id = 9
            WHERE pt.slot = 1
        ) t1 ON t1.pokemon_id = p.id
        LEFT JOIN (
            SELECT pt.pokemon_id, tn.name
            FROM pokemon_types pt
            JOIN type_names tn ON tn.type_id = pt.type_id AND tn.local_language_id = 9
            WHERE pt.slot = 2
        ) t2 ON t2.pokemon_id = p.id
        LEFT JOIN (
            SELECT pokemon_id,
                   MAX(CASE WHEN stat_id = 1 THEN base_stat END) AS hp,
                   MAX(CASE WHEN stat_id = 2 THEN base_stat END) AS attack,
                   MAX(CASE WHEN stat_id = 3 THEN base_stat END) AS defense,
                   MAX(CASE WHEN stat_id = 4 THEN base_stat END) AS special_attack,
                   MAX(CASE WHEN stat_id = 5 THEN base_stat END) AS special_defense,
                   MAX(CASE WHEN stat_id = 6 THEN base_stat END) AS speed
            FROM pokemon_stats GROUP BY pokemon_id
        ) st ON st.pokemon_id = p.id
        LEFT JOIN (
            SELECT species_id, flavor_text FROM (
                SELECT species_id, flavor_text,
                       ROW_NUMBER() OVER (PARTITION BY species_id ORDER BY version_id DESC) AS rn
                FROM pokemon_species_flavor_text WHERE language_id = 9
            ) WHERE rn = 1
        ) ft ON ft.species_id = s.id
        WHERE p.is_default = 1
    """,
    "v_type_matchup": """
        CREATE VIEW v_type_matchup AS
        SELECT
            a.name AS attacking,
            d.name AS defending,
            e.damage_factor / 100.0 AS multiplier
        FROM type_efficacy e
        JOIN type_names a ON a.type_id = e.damage_type_id AND a.local_language_id = 9
        JOIN type_names d ON d.type_id = e.target_type_id AND d.local_language_id = 9
    """,
    "v_evolution": """
        CREATE VIEW v_evolution AS
        SELECT chain_id, from_name, to_name, trigger, min_level FROM (
            SELECT
                child.evolution_chain_id AS chain_id,
                COALESCE(pn.name, parent.identifier) AS from_name,
                COALESCE(cn.name, child.identifier)  AS to_name,
                tr.identifier                        AS trigger,
                ev.minimum_level                     AS min_level,
                ROW_NUMBER() OVER (
                    PARTITION BY ev.evolved_species_id ORDER BY ev.id
                ) AS rn
            FROM pokemon_evolution ev
            JOIN pokemon_species child ON child.id = ev.evolved_species_id
            JOIN pokemon_species parent ON parent.id = child.evolves_from_species_id
            LEFT JOIN evolution_triggers tr ON tr.id = ev.evolution_trigger_id
            LEFT JOIN pokemon_species_names cn
                   ON cn.pokemon_species_id = child.id AND cn.local_language_id = 9
            LEFT JOIN pokemon_species_names pn
                   ON pn.pokemon_species_id = parent.id AND pn.local_language_id = 9
            -- pokemon_evolution has one row per game version group that shares the
            -- same evolution; is_default marks the canonical row per game, but
            -- regional-form species (e.g. Alolan Meowth) can still leave more than
            -- one is_default row for the same evolved species, each with a
            -- different trigger/level. rn = 1 collapses that down to exactly one
            -- row per real evolution, which is what a species-level chain needs.
            WHERE ev.is_default = 1
        ) WHERE rn = 1
    """,
    "v_pokemon_moves": """
        CREATE VIEW v_pokemon_moves AS
        SELECT DISTINCT
            vp.name        AS pokemon,
            mn.name        AS move,
            mm.identifier  AS method,
            pm.level       AS level,
            tn.name        AS move_type,
            m.power        AS power,
            m.accuracy     AS accuracy
        FROM pokemon_moves pm
        JOIN v_pokemon vp ON vp.id = pm.pokemon_id
        JOIN moves m ON m.id = pm.move_id
        LEFT JOIN move_names mn ON mn.move_id = m.id AND mn.local_language_id = 9
        LEFT JOIN pokemon_move_methods mm ON mm.id = pm.pokemon_move_method_id
        LEFT JOIN type_names tn ON tn.type_id = m.type_id AND tn.local_language_id = 9
    """,
}


def apply_views(conn: sqlite3.Connection) -> None:
    for ddl in VIEWS.values():
        conn.execute(ddl)
    conn.commit()
