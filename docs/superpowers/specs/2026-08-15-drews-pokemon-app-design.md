# Drew's Pokémon App — Design

Date: 2026-08-15
Status: Approved

## Purpose

A local app that answers Drew's questions about Pokémon. PokeAPI data lives in a
local SQLite database. An OpenAI model queries it through tools and answers in a
chat UI that renders real Pokémon cards and artwork inline.

Drew is a kid. The assistant is warm and enthusiastic, uses short sentences,
explains terms like "base stats" instead of assuming them, and leans on pictures.

## Question types it must handle

1. Factual lookup — "What are Gengar's abilities?"
2. Filtering and aggregation — "List every Water type under 10kg."
3. Comparison and reasoning — "Would Pikachu beat Onix?"
4. Team building — "Build me a team around Charizard."
5. Images — every answer that names a Pokémon can show it.

## Architecture

Three components, one repo, entirely local. No auth, no deploy.

```
pokemon_app/
  ingest/      Python. CSV dump -> pokedex.db. Run once.
  api/         Python. FastAPI + pydantic-ai agent (OpenAI). SSE streaming.
  web/         SvelteKit 2 / Svelte 5 runes. Chat UI.
  data/
    pokedex.db
    images/    downloaded artwork and sprites, served by FastAPI
  docs/
```

Development runs two processes: `uv run fastapi dev` on :8000 and
`npm run dev` on :5173, with Vite proxying `/api` and `/images` to :8000.

Python 3.12+, managed with uv. Ruff for lint and format. Type hints throughout,
Pydantic models for all data crossing a boundary.

## Component 1: Ingest

### Source of data

PokeAPI publishes its own source data as 184 CSV files in the `PokeAPI/pokeapi`
GitHub repo under `data/v2/csv/`. This is the same data the live REST API serves.
Ingesting the CSVs takes minutes instead of hours and avoids ~20,000 rate-limited
HTTP calls. The live REST API is not used.

Sprites and artwork live in the separate `PokeAPI/sprites` repo (~1.6GB total).
We sparse-clone only the directories we render.

### Entry point

`uv run python -m ingest.sync`

Flags:
- `--skip-images` — schema and data only, for fast iteration.
- `--force` — delete and rebuild `pokedex.db` from scratch.

The command is idempotent. Rerunning produces the same database.

### Steps

1. Sparse-clone `PokeAPI/pokeapi` at `data/v2/csv/` into a temp directory.
2. Create the SQLite schema, then load these CSVs:
   - `pokemon`, `pokemon_species`, `pokemon_forms`
   - `types`, `pokemon_types`, `type_efficacy`, `type_names`
   - `abilities`, `pokemon_abilities`, `ability_names`, `ability_flavor_text`
   - `stats`, `pokemon_stats`, `stat_names`
   - `moves`, `pokemon_moves`, `move_names`, `move_damage_classes`
   - `evolution_chains`, `pokemon_evolution`, `evolution_triggers`
   - `generations`, `generation_names`
   - `pokemon_species_names`, `pokemon_species_flavor_text`
   - `languages`, `version_groups`
3. Filter prose tables to English (`local_language_id = 9`) at load time.
4. Build denormalized views the agent queries instead of raw joins:
   - `v_pokemon` — one row per default Pokémon: id, name, generation, type1,
     type2, hp, attack, defense, special_attack, special_defense, speed,
     total_stats, height_m, weight_kg, artwork_path, sprite_path, flavor_text.
   - `v_type_matchup` — attacking type, defending type, multiplier.
   - `v_evolution` — from_name, to_name, trigger, min_level, chain_id.
   - `v_pokemon_moves` — pokemon name, move name, learn method, level, type,
     power, accuracy.
5. Create indexes on the columns the agent filters most: name, generation,
   type1, type2, total_stats.
6. Sparse-clone `PokeAPI/sprites` for `sprites/pokemon/other/official-artwork/`
   and `sprites/pokemon/*.png` into `data/images/`. Roughly 400MB and several
   minutes. Skipped by `--skip-images`.

### Verification

Ingest is not complete until these pass:
- Row counts logged per table, none zero.
- Spot checks: Pikachu is id 25, type electric, base speed 90. Charizard is
  fire/flying, generation 1. Water attacking Fire is 2x. Eevee's evolution chain
  returns 8 descendants.
- Every row in `v_pokemon` has a non-null `artwork_path` pointing at a file that
  exists on disk (when images were downloaded).

## Component 2: API and agent

FastAPI app. pydantic-ai v2 agent using the `openai:` provider. The model id
comes from an environment variable so it can be swapped without a code change.
Configuration via pydantic-settings, never hardcoded. The OpenAI API key is
read from the environment.

### Tools

Every tool returns a typed Pydantic model, never a raw string.

| Tool | Purpose |
|---|---|
| `find_pokemon(name_or_id)` | Fuzzy name resolution plus full profile. Most common call. |
| `type_matchup(attacking, defending)` | Type effectiveness. Precomputed because this is easy to get wrong in generated SQL. |
| `compare(names)` | Side-by-side stats and types for "would X beat Y". |
| `evolution_chain(name)` | Recursive walk of the evolution tree, wrapped so the model never writes the CTE. |
| `run_sql(query)` | Escape hatch for arbitrary filtering and aggregation. |

`find_pokemon` resolves names tolerantly: exact match, then case-insensitive,
then a trigram or Levenshtein fallback so "pikchu" and "mr mime" both work.
When no match is found it returns the closest candidates rather than an error,
so the model can ask Drew which one he meant.

### run_sql guardrails

- Executes on a separate SQLite connection opened read-only
  (`file:pokedex.db?mode=ro`).
- Rejects anything that is not a single `SELECT` statement. Multi-statement
  input, `DROP`, `DELETE`, `UPDATE`, `INSERT`, `ATTACH`, `PRAGMA`, and
  `CREATE` are all refused.
- A `LIMIT` is enforced, capped at 200 rows.
- Query timeout via `sqlite3` progress handler.
- Errors are returned to the model as text so it can correct and retry rather
  than failing the turn.

The system prompt contains the view definitions and column lists, and instructs
the model to prefer the views over the base tables.

### Streaming

`POST /api/chat` returns SSE. Three event types:

- `token` — a text delta.
- `tool` — tool name, arguments, and typed result, emitted when a tool returns.
- `done` — end of turn, with the persisted message id.

The frontend renders cards from `tool` event payloads, not by parsing prose out
of the model's text. This is the load-bearing decision: the cards are built from
typed data, so they are always correct even when the model's wording is loose.

### Persistence

`conversations` (id, title, created_at, updated_at) and `messages`
(id, conversation_id, role, content, tool_events_json, created_at) tables live
in the same `pokedex.db`. Conversation titles are generated from the first user
message. Endpoints: list conversations, get one, delete one.

## Component 3: Frontend

SvelteKit 2 with Svelte 5 runes. Tailwind CSS v4, configured in `globals.css`
via `@theme inline`, no `tailwind.config.ts`. Strict TypeScript, no `any`.

Single chat route plus a conversation sidebar. `$state` holds the message list.
An SSE reader appends tokens as they arrive and pushes tool events into the
message they belong to.

### Components

- `ChatMessage` — one turn, renders text plus any cards from its tool events.
- `ToolChip` — collapsed pill ("looked it up in the Pokédex"), expandable to
  show the SQL or tool arguments. Written so it reads fine to a kid.
- `PokemonCard` — large official artwork, name, number, type badges, stat bars
  with plain-language labels.
- `ComparisonTable` — two or more Pokémon side by side, higher stat highlighted.
- `TypeChart` — effectiveness grid for a matchup answer.
- `TeamGrid` — six slots for team-building answers.
- `EmptyState` — "Hey Drew, ask me anything about Pokémon" plus four clickable
  starter questions, one per question type, written for a kid.

Artwork is sized large. This is a kid's app and the pictures matter more than
information density.

## Branding

- Browser title and chat header: **Drew's Pokémon App**.
- Project names: `drews-pokemon-app` in both `package.json` and `pyproject.toml`.
- The system prompt states the app belongs to Drew and permits addressing him by
  name when it reads naturally. Not in every message.

## Testing

Run single tests with `uv run pytest`, not the full suite, unless asked.

- **Ingest**: row counts per table are non-zero; the spot checks listed under
  Verification above.
- **Agent**: `TestModel` and `FunctionModel` only. No live OpenAI calls in tests.
- **run_sql guardrails**: a dedicated suite asserting that `DROP`, `DELETE`,
  `ATTACH`, `PRAGMA`, multi-statement input, and missing `LIMIT` are all handled
  correctly.
- **Tools**: each tool tested against a small fixture database with known values.
- **Frontend**: component tests for `PokemonCard` and the SSE reader. No E2E.

## Out of scope

- Auth, Docker, and any deployment. This runs on Jordan's machine.
- Items, berries, machines, locations, encounters, contests.
- A battle simulator. "Would X beat Y" is the model reasoning over stats and
  type effectiveness, not a damage calculation. The assistant says so when the
  answer is a judgment call.
- The live PokeAPI REST endpoints at runtime. All data is local.

## Open risks

- The sprites clone is ~400MB and is the slowest part of setup. `--skip-images`
  exists so the rest can be built and tested without it.
- Generated SQL quality is the main quality risk. Mitigated by the denormalized
  views, the schema in the system prompt, and errors being returned to the model
  for retry.
- OpenAI cost per turn is small but not zero. The model id is configurable so a
  cheaper model can be used for everyday questions.
