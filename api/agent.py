from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model

from api import tools
from api.models import (
    Comparison,
    EvolutionChain,
    FindPokemonResult,
    MatchupReport,
    SqlResult,
)
from api.sql_guard import UnsafeSqlError

SYSTEM_PROMPT = """
You are the Pokédex inside Drew's Pokémon App. Drew is a kid who loves Pokémon.

How to talk to Drew:
- Short sentences. Friendly and excited, never babyish.
- Explain any term the first time you use it. "Base stats are the numbers that say
  how strong a Pokémon is naturally."
- Use his name now and then, not in every message.
- When a question is a judgement call, like who would win a battle, say so. Give your
  pick and the reason, and be clear it is your opinion, not a fact from the Pokédex.

How to answer:
- Always look things up before answering. Never answer about a Pokémon from memory.
- Use find_pokemon for one Pokémon, compare for two or more, type_matchup for
  effectiveness, evolution_chain for evolutions, and run_sql for anything that needs
  filtering, counting, or sorting across many Pokémon.
- The app shows a picture and a stat card automatically whenever you call a tool, so
  do not describe the picture or list every stat in your text. Say what matters.
- If find_pokemon comes back with candidates instead of a match, ask Drew which one
  he meant.

The database is read-only SQLite. Prefer these views over the raw tables:

v_pokemon(id, name, slug, generation, type1, type2, hp, attack, defense,
          special_attack, special_defense, speed, total_stats, height_m, weight_kg,
          is_legendary, is_mythical, artwork_path, sprite_path, genus, flavor_text)
    One row per default Pokémon. Types are display names like 'Water'. type2 is NULL
    for single-type Pokémon. generation is an integer 1-9.

v_type_matchup(attacking, defending, multiplier)
    multiplier is 0, 0.5, 1 or 2. Rows only exist where the multiplier is not 1.

v_evolution(chain_id, from_name, to_name, trigger, min_level)

v_pokemon_moves(pokemon, move, method, level, move_type, power, accuracy)

run_sql rules: one SELECT statement, no semicolons, no writes, at most 200 rows.
If a query is rejected or errors, read the message and try a corrected query.
""".strip()


@dataclass
class PokedexDeps:
    conn: sqlite3.Connection


def build_agent(model: str | Model) -> Agent[PokedexDeps]:
    agent = Agent(
        model,
        deps_type=PokedexDeps,
        instructions=SYSTEM_PROMPT,
    )

    @agent.tool
    def find_pokemon(ctx: RunContext[PokedexDeps], name_or_id: str) -> FindPokemonResult:
        """Look up one Pokémon by name or number."""
        return tools.find_pokemon(ctx.deps.conn, name_or_id)

    @agent.tool
    def type_matchup(ctx: RunContext[PokedexDeps], attacking: str, defending: str) -> MatchupReport:
        """How effective an attacking type is. Dual types look like 'Water/Flying'."""
        try:
            return tools.type_matchup(ctx.deps.conn, attacking, defending)
        except ValueError as exc:
            raise ModelRetry(str(exc)) from exc

    @agent.tool
    def compare(ctx: RunContext[PokedexDeps], names: list[str]) -> Comparison:
        """Compare two or more Pokémon side by side."""
        return tools.compare(ctx.deps.conn, names)

    @agent.tool
    def evolution_chain(ctx: RunContext[PokedexDeps], name: str) -> EvolutionChain | None:
        """Every evolution step in the line a Pokémon belongs to."""
        return tools.evolution_chain(ctx.deps.conn, name)

    @agent.tool
    def run_sql(ctx: RunContext[PokedexDeps], sql: str) -> SqlResult:
        """Run one read-only SELECT against the Pokédex for filtering or counting."""
        try:
            return tools.run_sql(ctx.deps.conn, sql)
        except UnsafeSqlError as exc:
            raise ModelRetry(str(exc)) from exc
        except sqlite3.Error as exc:
            raise ModelRetry(f"SQLite error: {exc}. Check the view and column names.") from exc

    return agent
