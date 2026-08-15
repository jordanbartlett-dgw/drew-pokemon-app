# Drew's Pokémon App Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A local chat app where Drew asks questions about Pokémon and gets kid-friendly answers backed by a local SQLite clone of PokeAPI, with artwork rendered inline.

**Architecture:** Python ingests PokeAPI's own CSV dump into `data/pokedex.db` and downloads artwork to `data/images/`. A FastAPI service runs a pydantic-ai v2 agent (OpenAI) with five tools over that database and streams text deltas plus typed tool results to the browser as SSE. A SvelteKit 2 / Svelte 5 frontend renders those tool results as Pokémon cards. In production one FastAPI process serves the built frontend, the API, and the images; a systemd user service keeps it running and `tailscale serve` publishes it to Drew's iPad over HTTPS.

**Tech Stack:** Python 3.12+ with uv, SQLite, FastAPI, pydantic-ai v2, pydantic-settings, ruff, pytest. SvelteKit 2, Svelte 5 runes, TypeScript strict, Tailwind CSS v4.

## Global Constraints

- Python 3.12+, managed with uv. Never call `pip` directly. Run tools via `uv run`.
- `from __future__ import annotations` at the top of every Python file.
- Type hints on every function. Pydantic `BaseModel` for all data crossing a boundary. `model_config = ConfigDict(...)`, never `class Config`.
- Configuration via pydantic-settings. No hardcoded paths, keys, or model ids.
- Default model is `openai:gpt-5.6-luna` ($0.20 per 1M input, $1.20 per 1M output). Every run carries `UsageLimits(request_limit=8, tool_calls_limit=12, total_tokens_limit=20000)`. Daily spend is capped at $0.25 and refused with a kid-friendly message, never a stack trace.
- Secrets come from Infisical, project `drew-pokemon`, injected by the CLI. There is no `.env` file and no `.env.example`. Every command that needs the OpenAI key is prefixed with `infisical run --`. `.infisical.json` is committed; it holds the project id and default environment, not secrets.
- Ruff for lint and format: `uv run ruff check --fix . && uv run ruff format .`
- pydantic-ai v2 only. Model strings carry a provider prefix (`openai:...`). `result.usage` is a property. No `instrument=`, `history_processors=`, `prepare_tools=`, or `event_stream_handler=` constructor args.
- Tests never call a live model. `models.ALLOW_MODEL_REQUESTS = False` in `tests/conftest.py`.
- Run single tests, not the whole suite, unless asked.
- TypeScript strict, no `any`. Tailwind v4 configured in `src/app.css` via `@theme inline`. No `tailwind.config.ts`.
- English rows in PokeAPI CSVs are `local_language_id = 9` (or `language_id = 9` in the flavor-text tables).
- User-facing copy is kid-friendly: short sentences, plain language, terms like "base stats" explained.
- App name is **Drew's Pokémon App** everywhere it is shown. Package name is `drews-pokemon-app`.
- Conventional commits: `feat:`, `fix:`, `docs:`, `chore:`, `refactor:`.
- Spec: `docs/superpowers/specs/2026-08-15-drews-pokemon-app-design.md`

## File Structure

```
pyproject.toml              uv project, deps, ruff + pytest config
.infisical.json             links this folder to the drew-pokemon project (committed)
.gitignore                  data/, .env, node_modules, __pycache__

api/settings.py             Settings (pydantic-settings) + get_settings()
api/app.py                  the ASGI entry point the dev server loads
api/budget.py               token pricing, usage log, daily cap
api/db.py                   read-only SQLite connections, query()
api/models.py               all Pydantic domain models
api/sql_guard.py            validate_sql(): SELECT-only, LIMIT enforcement
api/tools.py                the five agent tools
api/agent.py                agent assembly, system prompt, PokedexDeps
api/store.py                conversations + messages persistence
api/sse.py                  AgentStreamEvent -> SSE frames
api/main.py                 FastAPI app, routes, static image mount

ingest/source.py            sparse-clone PokeAPI repos
ingest/schema.py            CREATE TABLE statements
ingest/loader.py            CSV -> SQLite loading
ingest/views.py             CREATE VIEW statements
ingest/images.py            artwork + sprite extraction
ingest/sync.py              CLI orchestrator + verification

tests/conftest.py           anyio backend, ALLOW_MODEL_REQUESTS=False, fixture DB
tests/ingest/               loader, views, schema tests
tests/api/                  sql_guard, tools, agent, store, sse, routes tests

web/                        SvelteKit app (see Task 19 for internal layout)
deploy/drews-pokemon-app.service   systemd user unit
deploy/install.sh           build, install, enable, and tailscale serve
```

---

### Task 1: Project scaffold and settings

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `api/__init__.py`, `api/settings.py`, `tests/__init__.py`, `tests/conftest.py`
- Requires: `.infisical.json` linking this directory to the `drew-pokemon` project (Jordan runs `infisical init` once; see the note under Step 3)
- Test: `tests/api/test_settings.py`

**Interfaces:**
- Consumes: nothing
- Produces: `api.settings.Settings` with fields `openai_api_key: SecretStr`, `openai_model: str`, `db_path: Path`, `images_dir: Path`, `web_dist: Path`, `daily_budget_usd: float`, `request_limit: int`, `tool_calls_limit: int`, `total_tokens_limit: int`; and `get_settings() -> Settings` (cached).

- [ ] **Step 1: Initialise the uv project**

```bash
cd /home/jb/Developer/drew/pokemon_app
uv init --name drews-pokemon-app --python 3.12 --no-workspace --bare
uv add pydantic-ai fastapi pydantic-settings
uv add --dev pytest anyio ruff httpx
```

- [ ] **Step 2: Verify the OpenAI model id before hardcoding a default**

The default is `openai:gpt-5.6-luna`, chosen for price ($0.20 per 1M input, $1.20 per 1M output). Confirm that model exists on this account, and if not pick the newest available and use it as the default:

```bash
infisical run -- bash -c 'curl -s https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"' \
  | python3 -c "import json,sys; print([m['id'] for m in json.load(sys.stdin)['data'] if m['id'].startswith('gpt')])"
```

If this returns an auth error, the secret in Infisical is not named `OPENAI_API_KEY`. Check the names without printing values:

```bash
infisical run -- printenv | cut -d= -f1 | sort
```

- [ ] **Step 3: Confirm Infisical is linked, then write `.gitignore`**

`.infisical.json` must already exist in the project root, created by `infisical init` and pointing at the `drew-pokemon` project. That command is interactive, so Jordan runs it, not the implementer. Verify the link before going further:

```bash
infisical run -- printenv | grep -c OPENAI_API_KEY
```

Expected: `1`. If the file is missing you get `unknown flag` or a project-resolution error. Stop and ask Jordan to run `infisical init` rather than falling back to a `.env` file.

`.gitignore`:

```
.venv/
__pycache__/
*.pyc
.env
data/
node_modules/
web/.svelte-kit/
web/build/
.pytest_cache/
```

`.infisical.json` is deliberately not ignored. It carries the project id and default environment, no secrets.

- [ ] **Step 4: Write the failing test**

`tests/api/test_settings.py`:

```python
from __future__ import annotations

from pathlib import Path

from api.settings import Settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("POKEDEX_OPENAI_MODEL", "openai:gpt-test")
    settings = Settings()
    assert settings.openai_api_key.get_secret_value() == "sk-test"
    assert settings.openai_model == "openai:gpt-test"
    assert settings.db_path == Path("data/pokedex.db")
    assert settings.images_dir == Path("data/images")
    assert settings.web_dist == Path("web/build")


def test_settings_model_has_provider_prefix(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("POKEDEX_OPENAI_MODEL", raising=False)
    assert ":" in Settings().openai_model


def test_limit_defaults_are_conservative(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    settings = Settings()
    assert settings.daily_budget_usd == 0.25
    assert settings.request_limit == 8
    assert settings.tool_calls_limit == 12
    assert settings.total_tokens_limit == 20_000
```

- [ ] **Step 5: Run it and confirm it fails**

Run: `uv run pytest tests/api/test_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'api.settings'`

- [ ] **Step 6: Implement `api/settings.py`**

```python
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets arrive from Infisical via `infisical run --`."""

    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    openai_api_key: SecretStr
    openai_model: str = "openai:gpt-5.6-luna"
    db_path: Path = Path("data/pokedex.db")
    images_dir: Path = Path("data/images")
    web_dist: Path = Path("web/build")

    # Cost control. See api/budget.py.
    daily_budget_usd: float = 0.25
    request_limit: int = 8
    tool_calls_limit: int = 12
    total_tokens_limit: int = 20_000


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

Note: `openai_api_key` reads the unprefixed `OPENAI_API_KEY`, because that is the secret name in Infisical. Everything tunable gets a `POKEDEX_` alias so it can be overridden per environment without colliding with anything else. Import `Field` and use these declarations in place of the plain defaults above:

```python
from pydantic import Field, SecretStr

    openai_model: str = Field(default="openai:gpt-5.6-luna", alias="POKEDEX_OPENAI_MODEL")
    daily_budget_usd: float = Field(default=0.25, alias="POKEDEX_DAILY_BUDGET_USD")
    request_limit: int = Field(default=8, alias="POKEDEX_REQUEST_LIMIT")
    tool_calls_limit: int = Field(default=12, alias="POKEDEX_TOOL_CALLS_LIMIT")
    total_tokens_limit: int = Field(default=20_000, alias="POKEDEX_TOTAL_TOKENS_LIMIT")
```

`populate_by_name=True` is already set in `model_config`, so the field names still work too. All of these are optional in Infisical; the defaults apply when absent.

- [ ] **Step 7: Add pytest and ruff config to `pyproject.toml`**

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-q"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 8: Write `tests/conftest.py`**

```python
from __future__ import annotations

import pytest
from pydantic_ai import models

models.ALLOW_MODEL_REQUESTS = False


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
```

- [ ] **Step 9: Run the tests and confirm they pass**

Run: `uv run pytest tests/api/test_settings.py -v`
Expected: PASS, 3 passed

- [ ] **Step 10: Commit**

```bash
git add pyproject.toml uv.lock .gitignore .infisical.json api tests
git commit -m "feat: project scaffold and settings"
```

---

### Task 2: Ingest — sparse clone of the PokeAPI source repos

**Files:**
- Create: `ingest/__init__.py`, `ingest/source.py`
- Test: `tests/ingest/test_source.py`

**Interfaces:**
- Consumes: nothing
- Produces: `ingest.source.sparse_clone(repo_url: str, paths: list[str], dest: Path) -> Path` returning `dest`; `CSV_REPO`, `SPRITES_REPO`, `CSV_PATH_IN_REPO = "data/v2/csv"` constants.

- [ ] **Step 1: Write the failing test**

The clone itself is network work, so the test asserts the git commands are correct rather than hitting GitHub.

`tests/ingest/test_source.py`:

```python
from __future__ import annotations

from pathlib import Path

from ingest.source import CSV_REPO, sparse_clone


def test_sparse_clone_issues_expected_git_commands(tmp_path, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr("ingest.source.subprocess.run", fake_run)

    dest = tmp_path / "checkout"
    result = sparse_clone(CSV_REPO, ["data/v2/csv"], dest)

    assert result == dest
    assert calls[0][:3] == ["git", "clone", "--filter=blob:none"]
    assert "--sparse" in calls[0]
    assert CSV_REPO in calls[0]
    assert calls[1][:4] == ["git", "sparse-checkout", "set", "data/v2/csv"]


def test_sparse_clone_skips_when_already_present(tmp_path, monkeypatch):
    calls: list[list[str]] = []
    monkeypatch.setattr("ingest.source.subprocess.run", lambda cmd, **kw: calls.append(cmd))

    dest = tmp_path / "checkout"
    (dest / ".git").mkdir(parents=True)

    assert sparse_clone(CSV_REPO, ["data/v2/csv"], dest) == dest
    assert calls == []
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/ingest/test_source.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'ingest.source'`

- [ ] **Step 3: Implement `ingest/source.py`**

```python
from __future__ import annotations

import subprocess
from pathlib import Path

CSV_REPO = "https://github.com/PokeAPI/pokeapi.git"
SPRITES_REPO = "https://github.com/PokeAPI/sprites.git"
CSV_PATH_IN_REPO = "data/v2/csv"


def sparse_clone(repo_url: str, paths: list[str], dest: Path) -> Path:
    """Blobless sparse clone of `paths` from `repo_url` into `dest`.

    Skips the clone if `dest` already holds a git checkout, so reruns are cheap.
    """
    if (dest / ".git").exists():
        return dest

    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--filter=blob:none", "--sparse", "--depth", "1", repo_url, str(dest)],
        check=True,
    )
    subprocess.run(["git", "sparse-checkout", "set", *paths], cwd=dest, check=True)
    return dest
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/ingest/test_source.py -v`
Expected: PASS, 2 passed

- [ ] **Step 5: Sanity-check against the real repo once, by hand**

```bash
uv run python -c "
from pathlib import Path
from ingest.source import CSV_REPO, CSV_PATH_IN_REPO, sparse_clone
p = sparse_clone(CSV_REPO, [CSV_PATH_IN_REPO], Path('/tmp/pokeapi-src'))
print(len(list((p / CSV_PATH_IN_REPO).glob('*.csv'))), 'csv files')
"
```

Expected: `184 csv files`

- [ ] **Step 6: Commit**

```bash
git add ingest tests/ingest
git commit -m "feat: sparse clone of PokeAPI source repos"
```

---

### Task 3: Ingest — SQLite schema

**Files:**
- Create: `ingest/schema.py`
- Test: `tests/ingest/test_schema.py`

**Interfaces:**
- Consumes: nothing
- Produces: `ingest.schema.TABLES: dict[str, str]` mapping table name to its `CREATE TABLE` SQL, and `apply_schema(conn: sqlite3.Connection) -> None`.

The 26 source tables and their columns are fixed by the CSVs. Column names below were read from the live CSV headers and must match exactly.

- [ ] **Step 1: Write the failing test**

`tests/ingest/test_schema.py`:

```python
from __future__ import annotations

import sqlite3

from ingest.schema import TABLES, apply_schema


def test_apply_schema_creates_every_table():
    conn = sqlite3.connect(":memory:")
    apply_schema(conn)
    names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert set(TABLES) <= names


def test_pokemon_table_has_expected_columns():
    conn = sqlite3.connect(":memory:")
    apply_schema(conn)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(pokemon)")]
    assert cols == ["id", "identifier", "species_id", "height", "weight", "base_experience", "order_", "is_default"]


def test_type_efficacy_table_has_expected_columns():
    conn = sqlite3.connect(":memory:")
    apply_schema(conn)
    cols = [r[1] for r in conn.execute("PRAGMA table_info(type_efficacy)")]
    assert cols == ["damage_type_id", "target_type_id", "damage_factor"]
```

`order` is a reserved word in SQL, so the CSV column `order` becomes `order_` in SQLite. The loader in Task 4 handles that rename.

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/ingest/test_schema.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'ingest.schema'`

- [ ] **Step 3: Implement `ingest/schema.py`**

```python
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
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/ingest/test_schema.py -v`
Expected: PASS, 3 passed

- [ ] **Step 5: Commit**

```bash
git add ingest/schema.py tests/ingest/test_schema.py
git commit -m "feat: SQLite schema for PokeAPI source tables"
```

---

### Task 4: Ingest — CSV loader

**Files:**
- Create: `ingest/loader.py`
- Test: `tests/ingest/test_loader.py`

**Interfaces:**
- Consumes: `ingest.schema.TABLES`, `apply_schema`
- Produces: `ingest.loader.load_table(conn, table: str, csv_path: Path, english_only: bool = False) -> int` returning rows inserted; `ENGLISH_LANGUAGE_ID = 9`; `clean_flavor_text(raw: str) -> str`.

Behaviours the loader must have: rename the CSV column `order` to `order_`; convert empty strings to `NULL`; filter to English when `english_only` is set, using whichever of `local_language_id` or `language_id` the table has; strip the form feed and newline characters PokeAPI embeds in flavor text.

- [ ] **Step 1: Write the failing test**

`tests/ingest/test_loader.py`:

```python
from __future__ import annotations

import sqlite3

import pytest

from ingest.loader import clean_flavor_text, load_table
from ingest.schema import apply_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    apply_schema(c)
    return c


def write(tmp_path, name, text):
    p = tmp_path / f"{name}.csv"
    p.write_text(text)
    return p


def test_load_table_inserts_rows(conn, tmp_path):
    csv = write(tmp_path, "types", "id,identifier,generation_id,damage_class_id\n10,fire,1,3\n11,water,1,3\n")
    assert load_table(conn, "types", csv) == 2
    assert [r["identifier"] for r in conn.execute("SELECT identifier FROM types ORDER BY id")] == ["fire", "water"]


def test_load_table_renames_order_column(conn, tmp_path):
    csv = write(tmp_path, "pokemon", "id,identifier,species_id,height,weight,base_experience,order,is_default\n25,pikachu,25,4,60,112,32,1\n")
    load_table(conn, "pokemon", csv)
    row = conn.execute("SELECT * FROM pokemon").fetchone()
    assert row["order_"] == 32
    assert row["identifier"] == "pikachu"


def test_load_table_converts_empty_string_to_null(conn, tmp_path):
    csv = write(tmp_path, "moves", "id,identifier,generation_id,type_id,power,pp,accuracy,priority,target_id,damage_class_id,effect_id,effect_chance,contest_type_id,contest_effect_id,super_contest_effect_id\n1,pound,1,1,40,35,100,0,10,2,1,,5,1,5\n")
    load_table(conn, "moves", csv)
    assert conn.execute("SELECT effect_chance FROM moves").fetchone()[0] is None


def test_load_table_english_only_filters_local_language_id(conn, tmp_path):
    csv = write(tmp_path, "type_names", "type_id,local_language_id,name\n10,9,Fire\n10,5,Feu\n")
    assert load_table(conn, "type_names", csv, english_only=True) == 1
    assert conn.execute("SELECT name FROM type_names").fetchone()[0] == "Fire"


def test_load_table_english_only_filters_language_id(conn, tmp_path):
    csv = write(tmp_path, "pokemon_species_flavor_text", "species_id,version_id,language_id,flavor_text\n25,1,9,Zap!\n25,1,5,Zap en francais\n")
    assert load_table(conn, "pokemon_species_flavor_text", csv, english_only=True) == 1


def test_clean_flavor_text_strips_control_characters():
    assert clean_flavor_text("It keeps its\ftail\nraised.") == "It keeps its tail raised."
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/ingest/test_loader.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'ingest.loader'`

- [ ] **Step 3: Implement `ingest/loader.py`**

```python
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

        language_column = next(
            (c for c in _LANGUAGE_COLUMNS if c in source_columns), None
        )

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
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/ingest/test_loader.py -v`
Expected: PASS, 6 passed

- [ ] **Step 5: Commit**

```bash
git add ingest/loader.py tests/ingest/test_loader.py
git commit -m "feat: CSV loader with English filtering and column normalisation"
```

---

### Task 5: Ingest — denormalized views

**Files:**
- Create: `ingest/views.py`
- Test: `tests/ingest/test_views.py`

**Interfaces:**
- Consumes: `ingest.schema.apply_schema`, `ingest.loader.load_table`
- Produces: `ingest.views.VIEWS: dict[str, str]` and `apply_views(conn) -> None`. Views: `v_pokemon`, `v_type_matchup`, `v_evolution`, `v_pokemon_moves`.

Column contracts the agent tools in Tasks 10-14 depend on:

- `v_pokemon`: `id, name, slug, generation, type1, type2, hp, attack, defense, special_attack, special_defense, speed, total_stats, height_m, weight_kg, is_legendary, is_mythical, artwork_path, sprite_path, genus, flavor_text`
- `v_type_matchup`: `attacking, defending, multiplier`
- `v_evolution`: `chain_id, from_name, to_name, trigger, min_level`
- `v_pokemon_moves`: `pokemon, move, method, level, move_type, power, accuracy`

`height` is decimetres and `weight` is hectograms in the source data, so both are divided by 10. Stat ids are 1 hp, 2 attack, 3 defense, 4 special-attack, 5 special-defense, 6 speed. `damage_factor` is 0/50/100/200, so the multiplier is `damage_factor / 100.0`.

- [ ] **Step 1: Write the failing test**

`tests/ingest/test_views.py`:

```python
from __future__ import annotations

import sqlite3

import pytest

from ingest.schema import apply_schema
from ingest.views import apply_views


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    apply_schema(c)
    c.executescript(
        """
        INSERT INTO pokemon VALUES (25,'pikachu',25,4,60,112,32,1);
        INSERT INTO pokemon VALUES (26,'raichu',26,8,300,218,35,1);
        INSERT INTO pokemon_species (id,identifier,generation_id,evolves_from_species_id,evolution_chain_id,is_legendary,is_mythical)
            VALUES (25,'pikachu',1,172,10,0,0);
        INSERT INTO pokemon_species (id,identifier,generation_id,evolves_from_species_id,evolution_chain_id,is_legendary,is_mythical)
            VALUES (26,'raichu',1,25,10,0,0);
        INSERT INTO pokemon_species_names VALUES (25,9,'Pikachu','Mouse Pokémon');
        INSERT INTO pokemon_species_names VALUES (26,9,'Raichu','Mouse Pokémon');
        INSERT INTO pokemon_species_flavor_text VALUES (25,1,9,'Old entry.');
        INSERT INTO pokemon_species_flavor_text VALUES (25,40,9,'Newest entry.');
        INSERT INTO types VALUES (13,'electric',1,3);
        INSERT INTO types VALUES (5,'ground',1,2);
        INSERT INTO type_names VALUES (13,9,'Electric');
        INSERT INTO type_names VALUES (5,9,'Ground');
        INSERT INTO pokemon_types VALUES (25,13,1);
        INSERT INTO pokemon_types VALUES (26,13,1);
        INSERT INTO type_efficacy VALUES (5,13,200);
        INSERT INTO type_efficacy VALUES (13,5,0);
        INSERT INTO pokemon_stats VALUES (25,1,35,0),(25,2,55,0),(25,3,40,0),(25,4,50,0),(25,5,50,0),(25,6,90,0);
        INSERT INTO pokemon_stats VALUES (26,1,60,0),(26,2,90,0),(26,3,55,0),(26,4,90,0),(26,5,80,0),(26,6,110,0);
        INSERT INTO evolution_triggers VALUES (3,'use-item');
        INSERT INTO pokemon_evolution (id,evolved_species_id,evolution_trigger_id,minimum_level) VALUES (1,26,3,NULL);
        """
    )
    c.commit()
    apply_views(c)
    return c


def test_v_pokemon_shape(conn):
    row = conn.execute("SELECT * FROM v_pokemon WHERE id = 25").fetchone()
    assert row["name"] == "Pikachu"
    assert row["slug"] == "pikachu"
    assert row["type1"] == "Electric"
    assert row["type2"] is None
    assert row["speed"] == 90
    assert row["total_stats"] == 320
    assert row["height_m"] == 0.4
    assert row["weight_kg"] == 6.0
    assert row["generation"] == 1
    assert row["artwork_path"] == "official-artwork/25.png"
    assert row["sprite_path"] == "front-default/25.png"


def test_v_pokemon_uses_newest_flavor_text(conn):
    assert conn.execute("SELECT flavor_text FROM v_pokemon WHERE id = 25").fetchone()[0] == "Newest entry."


def test_v_type_matchup_multipliers(conn):
    rows = {(r["attacking"], r["defending"]): r["multiplier"] for r in conn.execute("SELECT * FROM v_type_matchup")}
    assert rows[("Ground", "Electric")] == 2.0
    assert rows[("Electric", "Ground")] == 0.0


def test_v_evolution_links_species(conn):
    row = conn.execute("SELECT * FROM v_evolution").fetchone()
    assert row["from_name"] == "Pikachu"
    assert row["to_name"] == "Raichu"
    assert row["trigger"] == "use-item"
    assert row["chain_id"] == 10
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/ingest/test_views.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'ingest.views'`

- [ ] **Step 3: Implement `ingest/views.py`**

```python
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
        SELECT
            child.evolution_chain_id AS chain_id,
            COALESCE(pn.name, parent.identifier) AS from_name,
            COALESCE(cn.name, child.identifier)  AS to_name,
            tr.identifier                        AS trigger,
            ev.minimum_level                     AS min_level
        FROM pokemon_evolution ev
        JOIN pokemon_species child ON child.id = ev.evolved_species_id
        JOIN pokemon_species parent ON parent.id = child.evolves_from_species_id
        LEFT JOIN evolution_triggers tr ON tr.id = ev.evolution_trigger_id
        LEFT JOIN pokemon_species_names cn
               ON cn.pokemon_species_id = child.id AND cn.local_language_id = 9
        LEFT JOIN pokemon_species_names pn
               ON pn.pokemon_species_id = parent.id AND pn.local_language_id = 9
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
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/ingest/test_views.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Commit**

```bash
git add ingest/views.py tests/ingest/test_views.py
git commit -m "feat: denormalized views for agent queries"
```

---

### Task 6: Ingest — artwork and sprites

**Files:**
- Create: `ingest/images.py`
- Test: `tests/ingest/test_images.py`

**Interfaces:**
- Consumes: `ingest.source.sparse_clone`, `ingest.source.SPRITES_REPO`
- Produces: `ingest.images.download_images(checkout: Path, images_dir: Path) -> int` returning files copied, and `SPRITE_PATHS: list[str]` naming the two sparse-checkout directories.

Layout inside the sprites repo: `sprites/pokemon/other/official-artwork/<id>.png` for the big art, `sprites/pokemon/<id>.png` for the small game sprite. These are copied to `<images_dir>/official-artwork/<id>.png` and `<images_dir>/front-default/<id>.png`, matching `artwork_path` and `sprite_path` in `v_pokemon`.

- [ ] **Step 1: Write the failing test**

`tests/ingest/test_images.py`:

```python
from __future__ import annotations

from ingest.images import download_images


def test_download_images_copies_into_expected_layout(tmp_path):
    checkout = tmp_path / "sprites"
    artwork = checkout / "sprites" / "pokemon" / "other" / "official-artwork"
    small = checkout / "sprites" / "pokemon"
    artwork.mkdir(parents=True)
    (artwork / "25.png").write_bytes(b"art")
    (small / "25.png").write_bytes(b"sprite")
    (small / "25-female.png").write_bytes(b"variant")

    images_dir = tmp_path / "images"
    copied = download_images(checkout, images_dir)

    assert (images_dir / "official-artwork" / "25.png").read_bytes() == b"art"
    assert (images_dir / "front-default" / "25.png").read_bytes() == b"sprite"
    assert not (images_dir / "front-default" / "25-female.png").exists()
    assert copied == 2


def test_download_images_is_idempotent(tmp_path):
    checkout = tmp_path / "sprites"
    small = checkout / "sprites" / "pokemon"
    small.mkdir(parents=True)
    (small / "1.png").write_bytes(b"sprite")

    images_dir = tmp_path / "images"
    assert download_images(checkout, images_dir) == 1
    assert download_images(checkout, images_dir) == 1
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/ingest/test_images.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'ingest.images'`

- [ ] **Step 3: Implement `ingest/images.py`**

```python
from __future__ import annotations

import shutil
from pathlib import Path

SPRITE_PATHS = [
    "sprites/pokemon/other/official-artwork",
    "sprites/pokemon",
]

_SOURCES = {
    "official-artwork": "sprites/pokemon/other/official-artwork",
    "front-default": "sprites/pokemon",
}


def download_images(checkout: Path, images_dir: Path) -> int:
    """Copy numeric-id PNGs out of a PokeAPI/sprites checkout into `images_dir`.

    Only `<id>.png` files are taken. Variant sprites such as `25-female.png` and
    the shiny/back subdirectories are skipped, which is what keeps this to a few
    hundred megabytes rather than the full 1.6GB repo.
    """
    copied = 0
    for target_name, source_rel in _SOURCES.items():
        source = checkout / source_rel
        if not source.is_dir():
            continue
        target = images_dir / target_name
        target.mkdir(parents=True, exist_ok=True)
        for png in source.glob("*.png"):
            if not png.stem.isdigit():
                continue
            destination = target / png.name
            if not destination.exists():
                shutil.copyfile(png, destination)
            copied += 1
    return copied
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/ingest/test_images.py -v`
Expected: PASS, 2 passed

- [ ] **Step 5: Commit**

```bash
git add ingest/images.py tests/ingest/test_images.py
git commit -m "feat: artwork and sprite extraction"
```

---

### Task 7: Ingest — orchestrator, CLI, and verification

**Files:**
- Create: `ingest/sync.py`
- Test: `tests/ingest/test_sync.py`

**Interfaces:**
- Consumes: everything from Tasks 2-6
- Produces: `ingest.sync.build_database(csv_dir: Path, db_path: Path) -> dict[str, int]` returning rows per table; `ingest.sync.verify(db_path: Path) -> list[str]` returning failure messages (empty means healthy); `main()` wired to `python -m ingest.sync`.

`ENGLISH_TABLES` is the set loaded with `english_only=True`: `type_names`, `ability_names`, `ability_flavor_text`, `stat_names`, `move_names`, `generation_names`, `pokemon_species_names`, `pokemon_species_flavor_text`.

- [ ] **Step 1: Write the failing test for `verify`**

`tests/ingest/test_sync.py`:

```python
from __future__ import annotations

import sqlite3

from ingest.schema import apply_schema
from ingest.sync import verify
from ingest.views import apply_views


def _seed(db_path, speed: int = 90, factor: int = 200):
    conn = sqlite3.connect(db_path)
    apply_schema(conn)
    conn.executescript(
        f"""
        INSERT INTO pokemon VALUES (25,'pikachu',25,4,60,112,32,1);
        INSERT INTO pokemon_species (id,identifier,generation_id,evolution_chain_id)
            VALUES (25,'pikachu',1,10);
        INSERT INTO pokemon_species_names VALUES (25,9,'Pikachu','Mouse Pokémon');
        INSERT INTO types VALUES (13,'electric',1,3);
        INSERT INTO types VALUES (11,'water',1,3);
        INSERT INTO types VALUES (10,'fire',1,3);
        INSERT INTO type_names VALUES (13,9,'Electric'),(11,9,'Water'),(10,9,'Fire');
        INSERT INTO pokemon_types VALUES (25,13,1);
        INSERT INTO type_efficacy VALUES (11,10,{factor});
        INSERT INTO pokemon_stats VALUES (25,1,35,0),(25,2,55,0),(25,3,40,0),(25,4,50,0),(25,5,50,0),(25,6,{speed},0);
        """
    )
    conn.commit()
    apply_views(conn)
    conn.close()


def test_verify_passes_on_healthy_database(tmp_path):
    db = tmp_path / "pokedex.db"
    _seed(db)
    assert verify(db) == []


def test_verify_reports_wrong_pikachu_speed(tmp_path):
    db = tmp_path / "pokedex.db"
    _seed(db, speed=60)
    failures = verify(db)
    assert any("speed" in f for f in failures)


def test_verify_reports_wrong_type_effectiveness(tmp_path):
    db = tmp_path / "pokedex.db"
    _seed(db, factor=100)
    failures = verify(db)
    assert any("Water" in f for f in failures)
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/ingest/test_sync.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'ingest.sync'`

- [ ] **Step 3: Implement `ingest/sync.py`**

```python
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
        copied = download_images(sprite_checkout, args.images_dir)
        print(f"  {copied:,} images")

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
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/ingest/test_sync.py -v`
Expected: PASS, 3 passed

- [ ] **Step 5: Run the real ingest without images**

```bash
uv run python -m ingest.sync --skip-images
```

Expected: row counts for all 28 tables, none zero, then `Verification passed.` If any table reports 0 rows, that CSV name is wrong in `TABLES` — fix it before continuing.

- [ ] **Step 6: Run the full ingest including images**

```bash
uv run python -m ingest.sync
```

Expected: several minutes, then a count of roughly 2,000+ images and `Verification passed.`

- [ ] **Step 7: Spot-check the data by hand**

```bash
uv run python -c "
import sqlite3
c = sqlite3.connect('data/pokedex.db'); c.row_factory = sqlite3.Row
for sql in [
  \"SELECT name, type1, type2, total_stats FROM v_pokemon WHERE slug='charizard'\",
  \"SELECT COUNT(*) AS n FROM v_pokemon WHERE type1='Water' AND weight_kg < 10\",
  \"SELECT to_name FROM v_evolution WHERE from_name='Eevee'\",
]:
    print(sql); print([dict(r) for r in c.execute(sql)]); print()
"
```

Expected: Charizard is Fire/Flying with 534 total stats; the Water count is non-zero; Eevee lists 8 evolutions.

- [ ] **Step 8: Commit**

```bash
git add ingest/sync.py tests/ingest/test_sync.py
git commit -m "feat: ingest orchestrator with verification"
```

---

### Task 8: Read-only database access

**Files:**
- Create: `api/db.py`
- Test: `tests/api/test_db.py`

**Interfaces:**
- Consumes: nothing
- Produces: `api.db.open_read_only(db_path: Path) -> sqlite3.Connection` and `api.db.query(conn, sql: str, params: tuple = ()) -> list[dict[str, Any]]`.

- [ ] **Step 1: Write the failing test**

`tests/api/test_db.py`:

```python
from __future__ import annotations

import sqlite3

import pytest

from api.db import open_read_only, query


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "pokedex.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE v_pokemon (id INTEGER, name TEXT)")
    conn.execute("INSERT INTO v_pokemon VALUES (25, 'Pikachu')")
    conn.commit()
    conn.close()
    return path


def test_query_returns_dicts(db_path):
    conn = open_read_only(db_path)
    assert query(conn, "SELECT * FROM v_pokemon") == [{"id": 25, "name": "Pikachu"}]


def test_query_accepts_parameters(db_path):
    conn = open_read_only(db_path)
    rows = query(conn, "SELECT name FROM v_pokemon WHERE id = ?", (25,))
    assert rows == [{"name": "Pikachu"}]


def test_connection_rejects_writes(db_path):
    conn = open_read_only(db_path)
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO v_pokemon VALUES (1, 'Bulbasaur')")


def test_open_read_only_raises_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        open_read_only(tmp_path / "nope.db")
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/api/test_db.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'api.db'`

- [ ] **Step 3: Implement `api/db.py`**

```python
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def open_read_only(db_path: Path) -> sqlite3.Connection:
    """Open the Pokédex read-only. Writes raise sqlite3.OperationalError."""
    if not db_path.exists():
        raise FileNotFoundError(
            f"{db_path} does not exist. Run `uv run python -m ingest.sync` first."
        )
    conn = sqlite3.connect(
        f"file:{db_path}?mode=ro", uri=True, check_same_thread=False
    )
    conn.row_factory = sqlite3.Row
    return conn


def query(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in conn.execute(sql, params)]
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/api/test_db.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Commit**

```bash
git add api/db.py tests/api/test_db.py
git commit -m "feat: read-only SQLite access layer"
```

---

### Task 9: Domain models

**Files:**
- Create: `api/models.py`
- Test: `tests/api/test_models.py`

**Interfaces:**
- Consumes: nothing
- Produces: the Pydantic models every tool, route, and the frontend types mirror.

These names are load-bearing. Later tasks reference them exactly as written.

- [ ] **Step 1: Write the failing test**

`tests/api/test_models.py`:

```python
from __future__ import annotations

from api.models import BaseStats, PokemonProfile, SqlResult, TypeMatchup


def test_base_stats_total():
    stats = BaseStats(hp=35, attack=55, defense=40, special_attack=50, special_defense=50, speed=90)
    assert stats.total == 320


def test_pokemon_profile_builds_image_urls():
    profile = PokemonProfile(
        id=25, name="Pikachu", slug="pikachu", generation=1, types=["Electric"],
        stats=BaseStats(hp=35, attack=55, defense=40, special_attack=50, special_defense=50, speed=90),
        height_m=0.4, weight_kg=6.0, abilities=["Static"],
        artwork_url="/images/official-artwork/25.png",
        sprite_url="/images/front-default/25.png",
    )
    assert profile.artwork_url.startswith("/images/")
    assert profile.genus is None
    assert profile.is_legendary is False


def test_type_matchup_label_reads_plainly():
    assert TypeMatchup(attacking="Water", defending="Fire", multiplier=2.0).label == "super effective"
    assert TypeMatchup(attacking="Fire", defending="Water", multiplier=0.5).label == "not very effective"
    assert TypeMatchup(attacking="Electric", defending="Ground", multiplier=0.0).label == "no effect"
    assert TypeMatchup(attacking="Normal", defending="Normal", multiplier=1.0).label == "normal damage"


def test_sql_result_flags_truncation():
    result = SqlResult(sql="SELECT 1", columns=["a"], rows=[{"a": 1}], row_count=1, truncated=False)
    assert result.truncated is False
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/api/test_models.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'api.models'`

- [ ] **Step 3: Implement `api/models.py`**

```python
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, computed_field


class BaseStats(BaseModel):
    model_config = ConfigDict(frozen=True)

    hp: int
    attack: int
    defense: int
    special_attack: int
    special_defense: int
    speed: int

    @computed_field
    @property
    def total(self) -> int:
        return (
            self.hp
            + self.attack
            + self.defense
            + self.special_attack
            + self.special_defense
            + self.speed
        )


class PokemonProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    name: str
    slug: str
    generation: int
    types: list[str]
    stats: BaseStats
    height_m: float
    weight_kg: float
    abilities: list[str]
    artwork_url: str
    sprite_url: str
    genus: str | None = None
    flavor_text: str | None = None
    is_legendary: bool = False
    is_mythical: bool = False


class FindPokemonResult(BaseModel):
    """Either a match, or the closest names so the model can ask Drew which he meant."""

    model_config = ConfigDict(frozen=True)

    pokemon: PokemonProfile | None = None
    candidates: list[str] = []


class TypeMatchup(BaseModel):
    model_config = ConfigDict(frozen=True)

    attacking: str
    defending: str
    multiplier: float

    @computed_field
    @property
    def label(self) -> str:
        if self.multiplier == 0:
            return "no effect"
        if self.multiplier > 1:
            return "super effective"
        if self.multiplier < 1:
            return "not very effective"
        return "normal damage"


class MatchupReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    attacking_types: list[str]
    defending_types: list[str]
    matchups: list[TypeMatchup]
    combined_multiplier: float


class Comparison(BaseModel):
    model_config = ConfigDict(frozen=True)

    pokemon: list[PokemonProfile]
    fastest: str
    highest_total: str


class EvolutionStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    from_name: str
    to_name: str
    trigger: str | None = None
    min_level: int | None = None


class EvolutionChain(BaseModel):
    model_config = ConfigDict(frozen=True)

    chain_id: int
    steps: list[EvolutionStep]


class SqlResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/api/test_models.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Commit**

```bash
git add api/models.py tests/api/test_models.py
git commit -m "feat: domain models"
```

---

### Task 10: SQL guardrails

**Files:**
- Create: `api/sql_guard.py`
- Test: `tests/api/test_sql_guard.py`

**Interfaces:**
- Consumes: nothing
- Produces: `api.sql_guard.UnsafeSqlError(Exception)`, `api.sql_guard.MAX_ROWS = 200`, and `api.sql_guard.validate_sql(sql: str) -> str` which returns the query with a `LIMIT` enforced or raises `UnsafeSqlError`.

- [ ] **Step 1: Write the failing test**

`tests/api/test_sql_guard.py`:

```python
from __future__ import annotations

import pytest

from api.sql_guard import MAX_ROWS, UnsafeSqlError, validate_sql


def test_adds_limit_when_missing():
    assert validate_sql("SELECT name FROM v_pokemon") == f"SELECT name FROM v_pokemon LIMIT {MAX_ROWS}"


def test_keeps_small_limit():
    assert validate_sql("SELECT name FROM v_pokemon LIMIT 5") == "SELECT name FROM v_pokemon LIMIT 5"


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
    out = validate_sql("WITH fast AS (SELECT * FROM v_pokemon WHERE speed > 100) SELECT name FROM fast")
    assert out.endswith(f"LIMIT {MAX_ROWS}")
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/api/test_sql_guard.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'api.sql_guard'`

- [ ] **Step 3: Implement `api/sql_guard.py`**

```python
from __future__ import annotations

import re

MAX_ROWS = 200

_FORBIDDEN = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|ATTACH|DETACH|PRAGMA|CREATE|REPLACE|VACUUM|REINDEX)\b",
    re.IGNORECASE,
)
_LIMIT = re.compile(r"\bLIMIT\s+(\d+)\s*$", re.IGNORECASE)


class UnsafeSqlError(Exception):
    """Raised when a generated query is not a plain, single, read-only SELECT."""


def validate_sql(sql: str) -> str:
    """Return `sql` with a row limit enforced, or raise UnsafeSqlError.

    The message on the exception is handed back to the model so it can retry,
    so it explains what is allowed rather than just refusing.
    """
    cleaned = sql.strip().rstrip(";").strip()

    if not cleaned:
        raise UnsafeSqlError("The query was empty. Write a single SELECT statement.")

    if ";" in cleaned:
        raise UnsafeSqlError("Only one statement is allowed. Remove the semicolon.")

    head = cleaned.lstrip("(").split(None, 1)[0].upper()
    if head not in {"SELECT", "WITH"}:
        raise UnsafeSqlError(
            f"Queries must start with SELECT or WITH, got {head}. This database is read-only."
        )

    if _FORBIDDEN.search(cleaned):
        raise UnsafeSqlError(
            "Only read-only SELECT queries are allowed. Nothing that changes or inspects "
            "the database structure."
        )

    match = _LIMIT.search(cleaned)
    if match is None:
        return f"{cleaned} LIMIT {MAX_ROWS}"
    if int(match.group(1)) > MAX_ROWS:
        return _LIMIT.sub(f"LIMIT {MAX_ROWS}", cleaned)
    return cleaned
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/api/test_sql_guard.py -v`
Expected: PASS, 15 passed

- [ ] **Step 5: Commit**

```bash
git add api/sql_guard.py tests/api/test_sql_guard.py
git commit -m "feat: read-only SQL guardrails"
```

---

### Task 11: Pokédex lookup — `find_pokemon`

**Files:**
- Create: `api/tools.py`
- Modify: `tests/conftest.py` (add the shared fixture database)
- Test: `tests/api/test_tools_find.py`

**Interfaces:**
- Consumes: `api.db.query`, `api.models.PokemonProfile`, `BaseStats`, `FindPokemonResult`
- Produces: `api.tools.find_pokemon(conn, name_or_id: str) -> FindPokemonResult` and `api.tools.load_profile(conn, pokemon_id: int) -> PokemonProfile | None`.

Resolution order: exact slug, then case-insensitive display name, then numeric id, then `difflib.get_close_matches` over all slugs. A miss returns candidates rather than raising, so the agent can ask Drew which one he meant.

- [ ] **Step 1: Add the shared fixture database to `tests/conftest.py`**

Append to the existing file:

```python
import sqlite3
from pathlib import Path

from api.db import open_read_only
from ingest.schema import apply_schema
from ingest.views import apply_views

_SEED = """
INSERT INTO pokemon VALUES (25,'pikachu',25,4,60,112,32,1);
INSERT INTO pokemon VALUES (26,'raichu',26,8,300,218,35,1);
INSERT INTO pokemon VALUES (6,'charizard',6,17,905,267,7,1);
INSERT INTO pokemon VALUES (7,'squirtle',7,5,90,63,10,1);
INSERT INTO pokemon_species (id,identifier,generation_id,evolves_from_species_id,evolution_chain_id,is_legendary,is_mythical)
    VALUES (25,'pikachu',1,NULL,10,0,0),
           (26,'raichu',1,25,10,0,0),
           (6,'charizard',1,5,2,0,0),
           (7,'squirtle',1,NULL,3,0,0);
INSERT INTO pokemon_species_names VALUES
    (25,9,'Pikachu','Mouse Pokémon'),
    (26,9,'Raichu','Mouse Pokémon'),
    (6,9,'Charizard','Flame Pokémon'),
    (7,9,'Squirtle','Tiny Turtle Pokémon');
INSERT INTO pokemon_species_flavor_text VALUES (25,40,9,'It raises its tail to check its surroundings.');
INSERT INTO types VALUES (13,'electric',1,3),(10,'fire',1,3),(3,'flying',1,2),(11,'water',1,3),(5,'ground',1,2);
INSERT INTO type_names VALUES (13,9,'Electric'),(10,9,'Fire'),(3,9,'Flying'),(11,9,'Water'),(5,9,'Ground');
INSERT INTO pokemon_types VALUES (25,13,1),(26,13,1),(6,10,1),(6,3,2),(7,11,1);
INSERT INTO type_efficacy VALUES
    (11,10,200),(10,11,50),(5,13,200),(13,5,0),(13,11,200),(13,3,200),(11,3,100);
INSERT INTO pokemon_stats VALUES
    (25,1,35,0),(25,2,55,0),(25,3,40,0),(25,4,50,0),(25,5,50,0),(25,6,90,0),
    (26,1,60,0),(26,2,90,0),(26,3,55,0),(26,4,90,0),(26,5,80,0),(26,6,110,0),
    (6,1,78,0),(6,2,84,0),(6,3,78,0),(6,4,109,0),(6,5,85,0),(6,6,100,0),
    (7,1,44,0),(7,2,48,0),(7,3,65,0),(7,4,50,0),(7,5,64,0),(7,6,43,0);
INSERT INTO abilities VALUES (9,'static',3,1),(66,'blaze',3,1),(67,'torrent',3,1);
INSERT INTO ability_names VALUES (9,9,'Static'),(66,9,'Blaze'),(67,9,'Torrent');
INSERT INTO pokemon_abilities VALUES (25,9,0,1),(26,9,0,1),(6,66,0,1),(7,67,0,1);
INSERT INTO evolution_triggers VALUES (1,'level-up'),(3,'use-item');
INSERT INTO pokemon_evolution (id,evolved_species_id,evolution_trigger_id,minimum_level)
    VALUES (1,26,3,NULL),(2,6,1,36);
"""


@pytest.fixture
def pokedex_path(tmp_path) -> Path:
    path = tmp_path / "pokedex.db"
    conn = sqlite3.connect(path)
    apply_schema(conn)
    conn.executescript(_SEED)
    conn.commit()
    apply_views(conn)
    conn.close()
    return path


@pytest.fixture
def pokedex(pokedex_path):
    return open_read_only(pokedex_path)
```

- [ ] **Step 2: Write the failing test**

`tests/api/test_tools_find.py`:

```python
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
```

- [ ] **Step 3: Run it and confirm it fails**

Run: `uv run pytest tests/api/test_tools_find.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'api.tools'`

- [ ] **Step 4: Implement `api/tools.py`**

```python
from __future__ import annotations

import difflib
import sqlite3
from typing import Any

from api.db import query
from api.models import BaseStats, FindPokemonResult, PokemonProfile

IMAGE_URL_PREFIX = "/images/"


def _abilities(conn: sqlite3.Connection, pokemon_id: int) -> list[str]:
    rows = query(
        conn,
        """
        SELECT an.name AS name
        FROM pokemon_abilities pa
        JOIN ability_names an ON an.ability_id = pa.ability_id AND an.local_language_id = 9
        WHERE pa.pokemon_id = ?
        ORDER BY pa.slot
        """,
        (pokemon_id,),
    )
    return [row["name"] for row in rows]


def _profile(conn: sqlite3.Connection, row: dict[str, Any]) -> PokemonProfile:
    types = [t for t in (row["type1"], row["type2"]) if t]
    return PokemonProfile(
        id=row["id"],
        name=row["name"],
        slug=row["slug"],
        generation=row["generation"],
        types=types,
        stats=BaseStats(
            hp=row["hp"],
            attack=row["attack"],
            defense=row["defense"],
            special_attack=row["special_attack"],
            special_defense=row["special_defense"],
            speed=row["speed"],
        ),
        height_m=row["height_m"],
        weight_kg=row["weight_kg"],
        abilities=_abilities(conn, row["id"]),
        artwork_url=f"{IMAGE_URL_PREFIX}{row['artwork_path']}",
        sprite_url=f"{IMAGE_URL_PREFIX}{row['sprite_path']}",
        genus=row["genus"],
        flavor_text=row["flavor_text"],
        is_legendary=bool(row["is_legendary"]),
        is_mythical=bool(row["is_mythical"]),
    )


def load_profile(conn: sqlite3.Connection, pokemon_id: int) -> PokemonProfile | None:
    rows = query(conn, "SELECT * FROM v_pokemon WHERE id = ?", (pokemon_id,))
    return _profile(conn, rows[0]) if rows else None


def find_pokemon(conn: sqlite3.Connection, name_or_id: str) -> FindPokemonResult:
    """Resolve a name, nickname-ish spelling, or number to one Pokémon."""
    needle = name_or_id.strip().lower().replace(" ", "-")

    rows = query(conn, "SELECT * FROM v_pokemon WHERE slug = ?", (needle,))
    if not rows:
        rows = query(conn, "SELECT * FROM v_pokemon WHERE LOWER(name) = ?", (needle,))
    if not rows and needle.isdigit():
        rows = query(conn, "SELECT * FROM v_pokemon WHERE id = ?", (int(needle),))
    if rows:
        return FindPokemonResult(pokemon=_profile(conn, rows[0]))

    slugs = [row["slug"] for row in query(conn, "SELECT slug FROM v_pokemon")]
    candidates = difflib.get_close_matches(needle, slugs, n=5, cutoff=0.7)
    return FindPokemonResult(pokemon=None, candidates=candidates)
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `uv run pytest tests/api/test_tools_find.py -v`
Expected: PASS, 6 passed

- [ ] **Step 6: Commit**

```bash
git add api/tools.py tests/conftest.py tests/api/test_tools_find.py
git commit -m "feat: find_pokemon lookup with fuzzy fallback"
```

---

### Task 12: Matchup, comparison, evolution, and SQL tools

**Files:**
- Modify: `api/tools.py`
- Test: `tests/api/test_tools_query.py`

**Interfaces:**
- Consumes: `api.tools.find_pokemon`, `load_profile`, `api.sql_guard.validate_sql`, `UnsafeSqlError`, `api.models.MatchupReport`, `TypeMatchup`, `Comparison`, `EvolutionChain`, `EvolutionStep`, `SqlResult`
- Produces:
  - `type_matchup(conn, attacking: str, defending: str) -> MatchupReport` — `defending` may be one type or two separated by `/`, and `combined_multiplier` is the product.
  - `compare(conn, names: list[str]) -> Comparison`
  - `evolution_chain(conn, name: str) -> EvolutionChain | None`
  - `run_sql(conn, sql: str) -> SqlResult` — raises `UnsafeSqlError` for rejected queries.

- [ ] **Step 1: Write the failing test**

`tests/api/test_tools_query.py`:

```python
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
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/api/test_tools_query.py -v`
Expected: FAIL, `ImportError: cannot import name 'compare' from 'api.tools'`

- [ ] **Step 3: Append to `api/tools.py`**

```python
from api.models import (
    Comparison,
    EvolutionChain,
    EvolutionStep,
    MatchupReport,
    SqlResult,
    TypeMatchup,
)
from api.sql_guard import MAX_ROWS, validate_sql


def _known_types(conn: sqlite3.Connection) -> dict[str, str]:
    rows = query(conn, "SELECT DISTINCT attacking AS name FROM v_type_matchup")
    rows += query(conn, "SELECT DISTINCT defending AS name FROM v_type_matchup")
    return {row["name"].lower(): row["name"] for row in rows}


def type_matchup(conn: sqlite3.Connection, attacking: str, defending: str) -> MatchupReport:
    """How much damage `attacking` does to `defending`. Dual types use 'Water/Flying'."""
    known = _known_types(conn)

    def resolve(name: str) -> str:
        key = name.strip().lower()
        if key not in known:
            raise ValueError(
                f"{name} is not a Pokémon type. Known types: {', '.join(sorted(known.values()))}"
            )
        return known[key]

    attack_type = resolve(attacking)
    defend_types = [resolve(part) for part in defending.split("/") if part.strip()]

    matchups: list[TypeMatchup] = []
    combined = 1.0
    for defend_type in defend_types:
        rows = query(
            conn,
            "SELECT multiplier FROM v_type_matchup WHERE attacking = ? AND defending = ?",
            (attack_type, defend_type),
        )
        multiplier = rows[0]["multiplier"] if rows else 1.0
        matchups.append(
            TypeMatchup(attacking=attack_type, defending=defend_type, multiplier=multiplier)
        )
        combined *= multiplier

    return MatchupReport(
        attacking_types=[attack_type],
        defending_types=defend_types,
        matchups=matchups,
        combined_multiplier=combined,
    )


def compare(conn: sqlite3.Connection, names: list[str]) -> Comparison:
    """Side-by-side profiles. Names that do not resolve are dropped."""
    profiles = [
        result.pokemon
        for result in (find_pokemon(conn, name) for name in names)
        if result.pokemon is not None
    ]
    if not profiles:
        return Comparison(pokemon=[], fastest="", highest_total="")

    fastest = max(profiles, key=lambda p: p.stats.speed)
    strongest = max(profiles, key=lambda p: p.stats.total)
    return Comparison(pokemon=profiles, fastest=fastest.name, highest_total=strongest.name)


def evolution_chain(conn: sqlite3.Connection, name: str) -> EvolutionChain | None:
    """Every step in the evolution line the named Pokémon belongs to."""
    found = find_pokemon(conn, name)
    if found.pokemon is None:
        return None

    chain_rows = query(
        conn,
        "SELECT evolution_chain_id AS chain_id FROM pokemon_species WHERE id = ?",
        (found.pokemon.id,),
    )
    if not chain_rows or chain_rows[0]["chain_id"] is None:
        return None
    chain_id = chain_rows[0]["chain_id"]

    steps = query(
        conn,
        "SELECT from_name, to_name, trigger, min_level FROM v_evolution WHERE chain_id = ?",
        (chain_id,),
    )
    return EvolutionChain(
        chain_id=chain_id,
        steps=[EvolutionStep(**step) for step in steps],
    )


def run_sql(conn: sqlite3.Connection, sql: str) -> SqlResult:
    """Run a read-only SELECT against the Pokédex. Raises UnsafeSqlError if rejected."""
    safe_sql = validate_sql(sql)
    rows = query(conn, safe_sql)
    columns = list(rows[0].keys()) if rows else []
    return SqlResult(
        sql=safe_sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
        truncated=len(rows) >= MAX_ROWS,
    )
```

Note: `api/tools.py` now has a `species_id` dependency on `pokemon_species`, which is a base table rather than a view. That is deliberate — `chain_id` is not exposed on `v_pokemon`.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/api/test_tools_query.py -v`
Expected: PASS, 12 passed

- [ ] **Step 5: Run every tool against the real database**

```bash
uv run python -c "
from pathlib import Path
from api.db import open_read_only
from api.tools import compare, evolution_chain, find_pokemon, run_sql, type_matchup
c = open_read_only(Path('data/pokedex.db'))
print(find_pokemon(c, 'gengar').pokemon.abilities)
print(type_matchup(c, 'Electric', 'Water/Flying').combined_multiplier)
print(compare(c, ['pikachu','onix']).fastest)
print([s.to_name for s in evolution_chain(c, 'eevee').steps])
print(run_sql(c, \"SELECT name, weight_kg FROM v_pokemon WHERE type1='Water' AND weight_kg < 10 ORDER BY weight_kg\").row_count)
"
```

Expected: Gengar's abilities list; `4.0`; `Pikachu`; 8 Eevee evolutions; a non-zero count of light Water types.

- [ ] **Step 6: Commit**

```bash
git add api/tools.py tests/api/test_tools_query.py
git commit -m "feat: matchup, comparison, evolution, and SQL tools"
```

---

### Task 13: Agent assembly

**Files:**
- Create: `api/agent.py`
- Test: `tests/api/test_agent.py`

**Interfaces:**
- Consumes: everything in `api.tools`, `api.sql_guard.UnsafeSqlError`
- Produces: `api.agent.PokedexDeps` (dataclass with `conn: sqlite3.Connection`), `api.agent.build_agent(model: str | Model) -> Agent[PokedexDeps]`, and `api.agent.SYSTEM_PROMPT`.

Tool errors are raised as `ModelRetry` so the model sees the message and corrects itself instead of the run failing. This is what makes the `run_sql` escape hatch usable.

- [ ] **Step 1: Write the failing test**

`tests/api/test_agent.py`:

```python
from __future__ import annotations

import pytest
from pydantic_ai import capture_run_messages
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from api.agent import SYSTEM_PROMPT, PokedexDeps, build_agent

pytestmark = pytest.mark.anyio


def test_system_prompt_mentions_drew_and_the_views():
    assert "Drew" in SYSTEM_PROMPT
    for view in ("v_pokemon", "v_type_matchup", "v_evolution", "v_pokemon_moves"):
        assert view in SYSTEM_PROMPT


async def test_agent_registers_all_five_tools(pokedex):
    agent = build_agent(TestModel())
    with capture_run_messages() as messages:
        await agent.run("Tell me about Pikachu", deps=PokedexDeps(conn=pokedex))

    called = {
        part.tool_name
        for message in messages
        if isinstance(message, ModelResponse)
        for part in message.parts
        if isinstance(part, ToolCallPart)
    }
    assert called == {"find_pokemon", "type_matchup", "compare", "evolution_chain", "run_sql"}


async def test_find_pokemon_tool_returns_a_profile(pokedex):
    def call_find(messages: list[ModelMessage], info: AgentInfo):
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("find_pokemon", {"name_or_id": "pikachu"})])
        return ModelResponse(parts=[TextPart("done")])

    agent = build_agent(FunctionModel(call_find))
    with capture_run_messages() as messages:
        await agent.run("Who is Pikachu?", deps=PokedexDeps(conn=pokedex))

    returned = [p for m in messages for p in m.parts if getattr(p, "part_kind", "") == "tool-return"]
    assert returned[0].content.pokemon.name == "Pikachu"


async def test_bad_sql_comes_back_as_a_retry_not_a_crash(pokedex):
    attempts: list[str] = []

    def call_sql(messages: list[ModelMessage], info: AgentInfo):
        if len(messages) == 1:
            attempts.append("bad")
            return ModelResponse(parts=[ToolCallPart("run_sql", {"sql": "DROP TABLE pokemon"})])
        if len(attempts) == 1:
            attempts.append("good")
            return ModelResponse(parts=[ToolCallPart("run_sql", {"sql": "SELECT name FROM v_pokemon"})])
        return ModelResponse(parts=[TextPart("Here you go, Drew!")])

    agent = build_agent(FunctionModel(call_sql))
    result = await agent.run("List them", deps=PokedexDeps(conn=pokedex))
    assert result.output == "Here you go, Drew!"
    assert attempts == ["bad", "good"]
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/api/test_agent.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'api.agent'`

- [ ] **Step 3: Implement `api/agent.py`**

```python
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
    def type_matchup(
        ctx: RunContext[PokedexDeps], attacking: str, defending: str
    ) -> MatchupReport:
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
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/api/test_agent.py -v`
Expected: PASS, 4 passed

- [ ] **Step 5: Ask the real model one question**

This is the first live OpenAI call. It costs a few cents.

```bash
infisical run -- uv run python -c "
import asyncio
from pathlib import Path
from api.agent import PokedexDeps, build_agent
from api.db import open_read_only
from api.settings import get_settings

async def main():
    agent = build_agent(get_settings().openai_model)
    conn = open_read_only(Path('data/pokedex.db'))
    r = await agent.run('Which Water type under 10kg is the fastest?', deps=PokedexDeps(conn=conn))
    print(r.output)
    print('tokens:', r.usage.input_tokens, r.usage.output_tokens)

asyncio.run(main())
"
```

Expected: a kid-friendly answer naming a real Pokémon, and a token count. If the model id is wrong you will get a 404 here. Fix the default in `api/settings.py` before continuing.

- [ ] **Step 6: Commit**

```bash
git add api/agent.py tests/api/test_agent.py
git commit -m "feat: pydantic-ai agent with Pokedex tools"
```

---

### Task 14: Conversation persistence

**Files:**
- Modify: `api/models.py` (add `ToolEvent`, `StoredTurn`, `ConversationSummary`)
- Create: `api/store.py`
- Test: `tests/api/test_store.py`

**Interfaces:**
- Consumes: `pydantic_ai.ModelMessagesTypeAdapter`
- Produces:
  - `api.models.ToolEvent(tool_name: str, args: dict[str, Any], result: Any)`
  - `api.models.StoredTurn(id: int, user_text: str, assistant_text: str, tool_events: list[ToolEvent], created_at: str)`
  - `api.models.ConversationSummary(id: int, title: str, created_at: str, updated_at: str, turn_count: int)`
  - `api.store.open_store(db_path) -> sqlite3.Connection`, `ensure_schema(conn)`, `create_conversation(conn, title) -> int`, `list_conversations(conn) -> list[ConversationSummary]`, `load_turns(conn, conversation_id) -> list[StoredTurn]`, `load_history(conn, conversation_id) -> list[ModelMessage]`, `save_turn(conn, conversation_id, user_text, assistant_text, tool_events, new_messages) -> int`, `delete_conversation(conn, conversation_id) -> None`, `title_from(user_text: str) -> str`.

One `turns` row per exchange holds both representations: the pydantic-ai messages that feed the next run, and the plain text plus tool events the UI renders.

- [ ] **Step 1: Write the failing test**

`tests/api/test_store.py`:

```python
from __future__ import annotations

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from api.models import ToolEvent
from api.store import (
    create_conversation,
    delete_conversation,
    ensure_schema,
    list_conversations,
    load_history,
    load_turns,
    open_store,
    save_turn,
    title_from,
)


def _store(pokedex_path):
    conn = open_store(pokedex_path)
    ensure_schema(conn)
    return conn


def _messages(text: str):
    return [
        ModelRequest(parts=[UserPromptPart(content=text)]),
        ModelResponse(parts=[TextPart(content="ok")]),
    ]


def test_title_from_truncates_long_questions():
    assert title_from("Who is Pikachu?") == "Who is Pikachu?"
    assert len(title_from("x" * 200)) <= 60


def test_save_and_load_a_turn(pokedex_path):
    conn = _store(pokedex_path)
    cid = create_conversation(conn, "Pikachu chat")
    events = [ToolEvent(tool_name="find_pokemon", args={"name_or_id": "pikachu"}, result={"id": 25})]
    save_turn(conn, cid, "Who is Pikachu?", "A mouse!", events, _messages("Who is Pikachu?"))

    turns = load_turns(conn, cid)
    assert len(turns) == 1
    assert turns[0].user_text == "Who is Pikachu?"
    assert turns[0].assistant_text == "A mouse!"
    assert turns[0].tool_events[0].tool_name == "find_pokemon"


def test_history_round_trips_pydantic_ai_messages(pokedex_path):
    conn = _store(pokedex_path)
    cid = create_conversation(conn, "chat")
    save_turn(conn, cid, "one", "ok", [], _messages("one"))
    save_turn(conn, cid, "two", "ok", [], _messages("two"))

    history = load_history(conn, cid)
    assert len(history) == 4
    assert isinstance(history[0], ModelRequest)


def test_list_conversations_counts_turns_newest_first(pokedex_path):
    conn = _store(pokedex_path)
    first = create_conversation(conn, "first")
    second = create_conversation(conn, "second")
    save_turn(conn, second, "q", "a", [], _messages("q"))

    summaries = list_conversations(conn)
    assert [s.id for s in summaries] == [second, first]
    assert summaries[0].turn_count == 1


def test_delete_removes_conversation_and_turns(pokedex_path):
    conn = _store(pokedex_path)
    cid = create_conversation(conn, "chat")
    save_turn(conn, cid, "q", "a", [], _messages("q"))
    delete_conversation(conn, cid)
    assert list_conversations(conn) == []
    assert load_turns(conn, cid) == []
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/api/test_store.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'api.store'`

- [ ] **Step 3: Add the three models to `api/models.py`**

```python
class ToolEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    tool_name: str
    args: dict[str, Any] = {}
    result: Any = None


class StoredTurn(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    user_text: str
    assistant_text: str
    tool_events: list[ToolEvent] = []
    created_at: str


class ConversationSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    title: str
    created_at: str
    updated_at: str
    turn_count: int
```

- [ ] **Step 4: Implement `api/store.py`**

```python
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from pydantic_ai import ModelMessagesTypeAdapter
from pydantic_ai.messages import ModelMessage
from pydantic_core import to_jsonable_python

from api.models import ConversationSummary, StoredTurn, ToolEvent

TITLE_MAX_LENGTH = 60

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_text TEXT NOT NULL,
    assistant_text TEXT NOT NULL,
    tool_events_json TEXT NOT NULL DEFAULT '[]',
    model_messages_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_turns_conversation ON turns(conversation_id);
"""


def open_store(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def title_from(user_text: str) -> str:
    collapsed = " ".join(user_text.split())
    if len(collapsed) <= TITLE_MAX_LENGTH:
        return collapsed
    return collapsed[: TITLE_MAX_LENGTH - 1].rstrip() + "…"


def create_conversation(conn: sqlite3.Connection, title: str) -> int:
    cursor = conn.execute("INSERT INTO conversations (title) VALUES (?)", (title,))
    conn.commit()
    return int(cursor.lastrowid)


def list_conversations(conn: sqlite3.Connection) -> list[ConversationSummary]:
    rows = conn.execute(
        """
        SELECT c.id, c.title, c.created_at, c.updated_at,
               (SELECT COUNT(*) FROM turns t WHERE t.conversation_id = c.id) AS turn_count
        FROM conversations c
        ORDER BY c.updated_at DESC, c.id DESC
        """
    ).fetchall()
    return [ConversationSummary(**dict(row)) for row in rows]


def load_turns(conn: sqlite3.Connection, conversation_id: int) -> list[StoredTurn]:
    rows = conn.execute(
        "SELECT id, user_text, assistant_text, tool_events_json, created_at "
        "FROM turns WHERE conversation_id = ? ORDER BY id",
        (conversation_id,),
    ).fetchall()
    return [
        StoredTurn(
            id=row["id"],
            user_text=row["user_text"],
            assistant_text=row["assistant_text"],
            tool_events=[ToolEvent(**e) for e in json.loads(row["tool_events_json"])],
            created_at=row["created_at"],
        )
        for row in rows
    ]


def load_history(conn: sqlite3.Connection, conversation_id: int) -> list[ModelMessage]:
    rows = conn.execute(
        "SELECT model_messages_json FROM turns WHERE conversation_id = ? ORDER BY id",
        (conversation_id,),
    ).fetchall()
    history: list[ModelMessage] = []
    for row in rows:
        history.extend(ModelMessagesTypeAdapter.validate_json(row["model_messages_json"]))
    return history


def save_turn(
    conn: sqlite3.Connection,
    conversation_id: int,
    user_text: str,
    assistant_text: str,
    tool_events: list[ToolEvent],
    new_messages: list[ModelMessage],
) -> int:
    cursor = conn.execute(
        "INSERT INTO turns (conversation_id, user_text, assistant_text, "
        "tool_events_json, model_messages_json) VALUES (?, ?, ?, ?, ?)",
        (
            conversation_id,
            user_text,
            assistant_text,
            json.dumps([e.model_dump() for e in tool_events]),
            json.dumps(to_jsonable_python(new_messages)),
        ),
    )
    conn.execute(
        "UPDATE conversations SET updated_at = datetime('now') WHERE id = ?",
        (conversation_id,),
    )
    conn.commit()
    return int(cursor.lastrowid)


def delete_conversation(conn: sqlite3.Connection, conversation_id: int) -> None:
    conn.execute("DELETE FROM turns WHERE conversation_id = ?", (conversation_id,))
    conn.execute("DELETE FROM conversations WHERE id = ?", (conversation_id,))
    conn.commit()
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `uv run pytest tests/api/test_store.py -v`
Expected: PASS, 5 passed

- [ ] **Step 6: Commit**

```bash
git add api/store.py api/models.py tests/api/test_store.py
git commit -m "feat: conversation and turn persistence"
```

---

### Task 14b: Token pricing and the daily budget

**Files:**
- Create: `api/budget.py`
- Test: `tests/api/test_budget.py`

**Interfaces:**
- Consumes: a writable connection from `api.store.open_store`
- Produces:
  - `api.budget.PRICING_USD_PER_MTOK: dict[str, tuple[float, float]]` — model id to (input, output) dollars per million tokens.
  - `api.budget.price_of(model: str, input_tokens: int, output_tokens: int) -> float`
  - `api.budget.ensure_schema(conn) -> None` — creates `usage_log`.
  - `api.budget.record_usage(conn, model, input_tokens, output_tokens) -> float` returning the cost of that turn.
  - `api.budget.spent_today(conn) -> float`
  - `api.budget.is_over_budget(conn, cap_usd: float) -> bool`
  - `api.budget.BUDGET_MESSAGE: str` — what Drew sees at the cap.

An unknown model is priced at the most expensive rate in the table. Under-counting would let the cap silently overspend, and this is a kid's app on Jordan's card.

The day boundary is local midnight, not UTC, because Drew's day is local.

- [ ] **Step 1: Write the failing test**

`tests/api/test_budget.py`:

```python
from __future__ import annotations

from api.budget import (
    PRICING_USD_PER_MTOK,
    BUDGET_MESSAGE,
    ensure_schema,
    is_over_budget,
    price_of,
    record_usage,
    spent_today,
)
from api.store import open_store


def _conn(pokedex_path):
    conn = open_store(pokedex_path)
    ensure_schema(conn)
    return conn


def test_pricing_table_has_the_default_model():
    assert PRICING_USD_PER_MTOK["openai:gpt-5.6-luna"] == (0.20, 1.20)


def test_price_of_known_model():
    # 1M input at $0.20 plus 1M output at $1.20
    assert price_of("openai:gpt-5.6-luna", 1_000_000, 1_000_000) == 1.40


def test_price_of_a_realistic_turn_is_about_a_tenth_of_a_cent():
    cost = price_of("openai:gpt-5.6-luna", 4_000, 300)
    assert 0.001 < cost < 0.002


def test_unknown_model_is_priced_at_the_most_expensive_rate():
    dearest = max(PRICING_USD_PER_MTOK.values(), key=lambda rate: rate[0] + rate[1])
    assert price_of("openai:something-new", 1_000_000, 1_000_000) == sum(dearest)


def test_record_usage_accumulates_across_turns(pokedex_path):
    conn = _conn(pokedex_path)
    assert spent_today(conn) == 0.0
    first = record_usage(conn, "openai:gpt-5.6-luna", 4_000, 300)
    second = record_usage(conn, "openai:gpt-5.6-luna", 4_000, 300)
    assert round(spent_today(conn), 8) == round(first + second, 8)


def test_is_over_budget_only_once_the_cap_is_reached(pokedex_path):
    conn = _conn(pokedex_path)
    assert is_over_budget(conn, 0.25) is False
    record_usage(conn, "openai:gpt-5.6-luna", 1_000_000, 0)  # $0.20
    assert is_over_budget(conn, 0.25) is False
    record_usage(conn, "openai:gpt-5.6-luna", 1_000_000, 0)  # $0.40 total
    assert is_over_budget(conn, 0.25) is True


def test_yesterdays_spend_does_not_count(pokedex_path):
    conn = _conn(pokedex_path)
    conn.execute(
        "INSERT INTO usage_log (day, model, input_tokens, output_tokens, cost_usd) "
        "VALUES (date('now','localtime','-1 day'), 'openai:gpt-5.6-luna', 1000000, 0, 0.20)"
    )
    conn.commit()
    assert spent_today(conn) == 0.0


def test_budget_message_is_kid_friendly():
    assert "Drew" in BUDGET_MESSAGE
    assert "tomorrow" in BUDGET_MESSAGE.lower()
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/api/test_budget.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'api.budget'`

- [ ] **Step 3: Implement `api/budget.py`**

```python
from __future__ import annotations

import sqlite3

# Dollars per million tokens, (input, output).
# Source: https://developers.openai.com/api/docs/pricing, checked 2026-08-15.
# Update this table when the model changes or prices move.
PRICING_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "openai:gpt-5.6-luna": (0.20, 1.20),
    "openai:gpt-5-nano": (0.05, 0.40),
    "openai:gpt-5.4-nano": (0.20, 1.25),
    "openai:gpt-5-mini": (0.25, 2.00),
}

BUDGET_MESSAGE = (
    "That's all the Pokémon questions for today, Drew. Come back tomorrow!"
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL DEFAULT (date('now','localtime')),
    model TEXT NOT NULL,
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_usage_day ON usage_log(day);
"""


def _dearest_rate() -> tuple[float, float]:
    return max(PRICING_USD_PER_MTOK.values(), key=lambda rate: rate[0] + rate[1])


def price_of(model: str, input_tokens: int, output_tokens: int) -> float:
    """Cost in dollars. Unknown models are priced at the most expensive known rate."""
    input_rate, output_rate = PRICING_USD_PER_MTOK.get(model, _dearest_rate())
    return (input_tokens * input_rate + output_tokens * output_rate) / 1_000_000


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def record_usage(
    conn: sqlite3.Connection, model: str, input_tokens: int, output_tokens: int
) -> float:
    cost = price_of(model, input_tokens, output_tokens)
    conn.execute(
        "INSERT INTO usage_log (model, input_tokens, output_tokens, cost_usd) "
        "VALUES (?, ?, ?, ?)",
        (model, input_tokens, output_tokens, cost),
    )
    conn.commit()
    return cost


def spent_today(conn: sqlite3.Connection) -> float:
    row = conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM usage_log "
        "WHERE day = date('now','localtime')"
    ).fetchone()
    return float(row["total"])


def is_over_budget(conn: sqlite3.Connection, cap_usd: float) -> bool:
    return spent_today(conn) >= cap_usd
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/api/test_budget.py -v`
Expected: PASS, 8 passed

- [ ] **Step 5: Commit**

```bash
git add api/budget.py tests/api/test_budget.py
git commit -m "feat: token pricing and daily budget cap"
```

---

### Task 15: SSE event mapping

**Files:**
- Create: `api/sse.py`
- Test: `tests/api/test_sse.py`

**Interfaces:**
- Consumes: `api.agent.build_agent`, `PokedexDeps`, `api.models.ToolEvent`
- Produces:
  - `api.sse.frame(event: str, data: dict[str, Any]) -> str` — one SSE frame, `event:` line plus `data:` line plus blank line.
  - `api.sse.TurnRecorder` dataclass with `text: str`, `tool_events: list[ToolEvent]`, `new_messages: list[ModelMessage]`, `input_tokens: int`, `output_tokens: int`.
  - `api.sse.stream_turn(agent, deps, prompt, history, recorder, usage_limits) -> AsyncIterator[str]` yielding `token`, `tool`, `limit`, and `error` frames. The caller emits `start` and `done`.

`UsageLimitExceeded` is caught separately from other errors. A runaway tool loop is an expected condition here, not a crash, and Drew must see a sentence rather than a traceback. The tokens burned before the limit tripped are still recorded on the recorder so they count against the daily budget.

Tool arguments arrive on `FunctionToolCallEvent` and results on `FunctionToolResultEvent`, matched by `tool_call_id`. A `ModelRetry` surfaces as a retry-prompt part rather than a tool return, and is not emitted to the UI.

- [ ] **Step 1: Write the failing test**

`tests/api/test_sse.py`:

```python
from __future__ import annotations

import json

import pytest
from pydantic_ai import UsageLimits
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from api.agent import PokedexDeps, build_agent
from api.sse import TurnRecorder, frame, stream_turn

pytestmark = pytest.mark.anyio


def test_frame_format():
    assert frame("token", {"text": "hi"}) == 'event: token\ndata: {"text": "hi"}\n\n'


def _parse(frames: list[str]) -> list[tuple[str, dict]]:
    parsed = []
    for raw in frames:
        lines = raw.strip().split("\n")
        parsed.append((lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))))
    return parsed


async def test_streams_tokens_and_tool_results(pokedex):
    def script(messages: list[ModelMessage], info: AgentInfo):
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("find_pokemon", {"name_or_id": "pikachu"})])
        return ModelResponse(parts=[TextPart("Pikachu is an Electric mouse!")])

    recorder = TurnRecorder()
    agent = build_agent(FunctionModel(script))
    frames = [
        f
        async for f in stream_turn(agent, PokedexDeps(conn=pokedex), "Who is Pikachu?", [], recorder)
    ]
    events = _parse(frames)

    tool_events = [d for name, d in events if name == "tool"]
    assert tool_events[0]["tool_name"] == "find_pokemon"
    assert tool_events[0]["args"] == {"name_or_id": "pikachu"}
    assert tool_events[0]["result"]["pokemon"]["name"] == "Pikachu"

    text = "".join(d["text"] for name, d in events if name == "token")
    assert text == "Pikachu is an Electric mouse!"


async def test_recorder_captures_turn_state(pokedex):
    def script(messages: list[ModelMessage], info: AgentInfo):
        if len(messages) == 1:
            return ModelResponse(parts=[ToolCallPart("find_pokemon", {"name_or_id": "pikachu"})])
        return ModelResponse(parts=[TextPart("All done, Drew!")])

    recorder = TurnRecorder()
    agent = build_agent(FunctionModel(script))
    async for _ in stream_turn(agent, PokedexDeps(conn=pokedex), "Who?", [], recorder):
        pass

    assert recorder.text == "All done, Drew!"
    assert recorder.tool_events[0].tool_name == "find_pokemon"
    assert len(recorder.new_messages) >= 2


async def test_usage_limit_emits_a_limit_frame_not_an_error(pokedex):
    def loop(messages: list[ModelMessage], info: AgentInfo):
        return ModelResponse(parts=[ToolCallPart("find_pokemon", {"name_or_id": "pikachu"})])

    recorder = TurnRecorder()
    agent = build_agent(FunctionModel(loop))
    frames = [
        f
        async for f in stream_turn(
            agent,
            PokedexDeps(conn=pokedex),
            "loop forever",
            [],
            recorder,
            UsageLimits(request_limit=3),
        )
    ]
    names = [name for name, _ in _parse(frames)]
    assert names[-1] == "limit"
    assert "Drew" in _parse(frames)[-1][1]["message"]


async def test_model_failure_emits_an_error_frame(pokedex):
    def boom(messages: list[ModelMessage], info: AgentInfo):
        raise RuntimeError("provider exploded")

    recorder = TurnRecorder()
    agent = build_agent(FunctionModel(boom))
    frames = [
        f async for f in stream_turn(agent, PokedexDeps(conn=pokedex), "Who?", [], recorder)
    ]
    names = [name for name, _ in _parse(frames)]
    assert names[-1] == "error"
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/api/test_sse.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'api.sse'`

- [ ] **Step 3: Implement `api/sse.py`**

```python
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    TextPartDelta,
    UsageLimitExceeded,
    UsageLimits,
)
from pydantic_ai.messages import ModelMessage
from pydantic_core import to_jsonable_python

from api.agent import PokedexDeps
from api.models import ToolEvent


def frame(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


LIMIT_MESSAGE = (
    "Whoa, that question sent me in circles! Try asking it a different way, Drew."
)


@dataclass
class TurnRecorder:
    """Collects what the turn produced so the caller can persist and bill it."""

    text: str = ""
    tool_events: list[ToolEvent] = field(default_factory=list)
    new_messages: list[ModelMessage] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0


async def stream_turn(
    agent: Agent[PokedexDeps],
    deps: PokedexDeps,
    prompt: str,
    history: list[ModelMessage],
    recorder: TurnRecorder,
    usage_limits: UsageLimits | None = None,
) -> AsyncIterator[str]:
    pending_args: dict[str, dict[str, Any]] = {}
    chunks: list[str] = []

    try:
        async with agent.run_stream_events(
            prompt, deps=deps, message_history=history, usage_limits=usage_limits
        ) as events:
            async for event in events:
                if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
                    chunks.append(event.delta.content_delta)
                    yield frame("token", {"text": event.delta.content_delta})

                elif isinstance(event, FunctionToolCallEvent):
                    args = event.part.args
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {"raw": args}
                    pending_args[event.part.tool_call_id] = args or {}

                elif isinstance(event, FunctionToolResultEvent):
                    if getattr(event.part, "part_kind", "") != "tool-return":
                        continue
                    tool_event = ToolEvent(
                        tool_name=event.part.tool_name,
                        args=pending_args.pop(event.tool_call_id, {}),
                        result=to_jsonable_python(event.part.content),
                    )
                    recorder.tool_events.append(tool_event)
                    yield frame("tool", tool_event.model_dump())

                elif isinstance(event, AgentRunResultEvent):
                    recorder.new_messages = event.result.new_messages()
                    recorder.text = "".join(chunks) or str(event.result.output)
                    recorder.input_tokens = event.result.usage.input_tokens
                    recorder.output_tokens = event.result.usage.output_tokens
    except UsageLimitExceeded:
        recorder.text = "".join(chunks) or LIMIT_MESSAGE
        yield frame("limit", {"message": LIMIT_MESSAGE})
    except Exception as exc:  # noqa: BLE001 - surfaced to the browser, not swallowed
        recorder.text = "".join(chunks)
        yield frame("error", {"message": f"{type(exc).__name__}: {exc}"})
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/api/test_sse.py -v`
Expected: PASS, 5 passed

- [ ] **Step 5: Commit**

```bash
git add api/sse.py tests/api/test_sse.py
git commit -m "feat: map agent stream events to SSE frames"
```

---

### Task 16: FastAPI application

**Files:**
- Create: `api/main.py`, `api/app.py`
- Test: `tests/api/test_routes.py`

**Interfaces:**
- Consumes: everything in `api.*`
- Produces: `api.main.create_app(db_path, images_dir, model, web_dist=None, daily_budget_usd=0.25, usage_limits=None) -> FastAPI`, and `api.app.app`, the default instance built from `get_settings()`.

The two modules are separate on purpose. `api/main.py` holds only the factory, so importing it in tests needs neither an OpenAI key nor a built database. `api/app.py` is the entry point the dev server loads, and it does require both.

Routes:

| Method | Path | Behaviour |
|---|---|---|
| `POST` | `/api/chat` | Body `{"message": str, "conversation_id": int \| null}`. SSE stream: `start` (with `conversation_id` and `title`), then `token`/`tool`, then `done`. Persists the turn before `done`. |
| `GET` | `/api/conversations` | List summaries, newest first. |
| `GET` | `/api/conversations/{id}` | `{"conversation": summary, "turns": [...]}`. 404 if unknown. |
| `DELETE` | `/api/conversations/{id}` | 204. |
| `GET` | `/api/health` | `{"status": "ok", "pokemon_count": int, "spent_today_usd": float, "daily_budget_usd": float}`. |
| `GET` | `/images/...` | Static files from `images_dir`. |
| `GET` | `/...` | The built SvelteKit app from `web_dist`, when that directory exists. Mounted last so it never shadows the API. |

Two cost behaviours live here. Before a turn starts, if today's spend is at the cap the app emits a `limit` frame with `BUDGET_MESSAGE` and never calls the model. After a turn ends, the recorded token counts are priced and logged, including the tokens burned by a turn that hit `UsageLimitExceeded`.

- [ ] **Step 1: Write the failing test**

`tests/api/test_routes.py`:

```python
from __future__ import annotations

import json

import httpx
import pytest
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel

from api.budget import ensure_schema as ensure_budget_schema
from api.budget import record_usage
from api.main import create_app
from api.store import open_store

pytestmark = pytest.mark.anyio


def _script(messages: list[ModelMessage], info: AgentInfo):
    if len(messages) == 1:
        return ModelResponse(parts=[ToolCallPart("find_pokemon", {"name_or_id": "pikachu"})])
    return ModelResponse(parts=[TextPart("Pikachu is quick!")])


@pytest.fixture
def client(pokedex_path, tmp_path):
    app = create_app(db_path=pokedex_path, images_dir=tmp_path, model=FunctionModel(_script))
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _events(body: str) -> list[tuple[str, dict]]:
    out = []
    for block in body.strip().split("\n\n"):
        lines = block.split("\n")
        out.append((lines[0].removeprefix("event: "), json.loads(lines[1].removeprefix("data: "))))
    return out


async def test_health_reports_pokemon_count(client):
    async with client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["pokemon_count"] == 4


async def test_chat_streams_and_persists(client):
    async with client:
        response = await client.post("/api/chat", json={"message": "Who is Pikachu?"})
        events = _events(response.text)

        assert events[0][0] == "start"
        conversation_id = events[0][1]["conversation_id"]
        assert events[0][1]["title"] == "Who is Pikachu?"
        assert any(name == "tool" for name, _ in events)
        assert "".join(d["text"] for n, d in events if n == "token") == "Pikachu is quick!"
        assert events[-1][0] == "done"

        detail = await client.get(f"/api/conversations/{conversation_id}")

    body = detail.json()
    assert body["turns"][0]["assistant_text"] == "Pikachu is quick!"
    assert body["turns"][0]["tool_events"][0]["tool_name"] == "find_pokemon"


async def test_chat_continues_an_existing_conversation(client):
    async with client:
        first = await client.post("/api/chat", json={"message": "Who is Pikachu?"})
        conversation_id = _events(first.text)[0][1]["conversation_id"]

        await client.post(
            "/api/chat", json={"message": "And Raichu?", "conversation_id": conversation_id}
        )
        listing = await client.get("/api/conversations")
        detail = await client.get(f"/api/conversations/{conversation_id}")

    assert len(listing.json()) == 1
    assert listing.json()[0]["turn_count"] == 2
    assert len(detail.json()["turns"]) == 2


async def test_unknown_conversation_is_404(client):
    async with client:
        response = await client.get("/api/conversations/999")
    assert response.status_code == 404


async def test_delete_conversation(client):
    async with client:
        created = await client.post("/api/chat", json={"message": "Who is Pikachu?"})
        conversation_id = _events(created.text)[0][1]["conversation_id"]
        deleted = await client.delete(f"/api/conversations/{conversation_id}")
        listing = await client.get("/api/conversations")

    assert deleted.status_code == 204
    assert listing.json() == []


async def test_empty_message_is_rejected(client):
    async with client:
        response = await client.post("/api/chat", json={"message": "   "})
    assert response.status_code == 422


async def test_health_reports_budget(client):
    async with client:
        body = (await client.get("/api/health")).json()
    assert body["daily_budget_usd"] == 0.25
    assert body["spent_today_usd"] == 0.0


async def test_over_budget_never_calls_the_model(pokedex_path, tmp_path):
    calls: list[int] = []

    def counting(messages, info):
        calls.append(1)
        return ModelResponse(parts=[TextPart("should not happen")])

    app = create_app(
        db_path=pokedex_path,
        images_dir=tmp_path,
        model=FunctionModel(counting),
        daily_budget_usd=0.0001,
    )
    conn = open_store(pokedex_path)
    ensure_budget_schema(conn)
    record_usage(conn, "openai:gpt-5.6-luna", 1_000_000, 0)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/chat", json={"message": "Who is Pikachu?"})

    events = _events(response.text)
    assert [name for name, _ in events] == ["start", "limit", "done"]
    assert "tomorrow" in events[1][1]["message"].lower()
    assert calls == []


async def test_usage_is_recorded_after_a_turn(client, pokedex_path):
    async with client:
        await client.post("/api/chat", json={"message": "Who is Pikachu?"})
        body = (await client.get("/api/health")).json()
    assert body["spent_today_usd"] > 0
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `uv run pytest tests/api/test_routes.py -v`
Expected: FAIL, `ModuleNotFoundError: No module named 'api.main'`

- [ ] **Step 3: Implement `api/main.py`**

```python
from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import UsageLimits
from pydantic_ai.models import Model

from api.agent import PokedexDeps, build_agent
from api.budget import BUDGET_MESSAGE, is_over_budget, record_usage, spent_today
from api.budget import ensure_schema as ensure_budget_schema
from api.db import open_read_only, query
from api.sse import TurnRecorder, frame, stream_turn
from api.store import (
    create_conversation,
    delete_conversation,
    ensure_schema,
    list_conversations,
    load_history,
    load_turns,
    open_store,
    save_turn,
    title_from,
)

APP_NAME = "Drew's Pokémon App"


class ChatRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: str = Field(min_length=1)
    conversation_id: int | None = None


def create_app(
    db_path: Path,
    images_dir: Path,
    model: str | Model,
    web_dist: Path | None = None,
    daily_budget_usd: float = 0.25,
    usage_limits: UsageLimits | None = None,
) -> FastAPI:
    app = FastAPI(title=APP_NAME)

    read_conn = open_read_only(db_path)
    store_conn = open_store(db_path)
    ensure_schema(store_conn)
    ensure_budget_schema(store_conn)
    agent = build_agent(model)
    model_id = model if isinstance(model, str) else getattr(model, "model_name", "unknown")

    images_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/images", StaticFiles(directory=images_dir), name="images")

    @app.get("/api/health")
    def health() -> dict[str, object]:
        count = query(read_conn, "SELECT COUNT(*) AS n FROM v_pokemon")[0]["n"]
        return {
            "status": "ok",
            "app": APP_NAME,
            "pokemon_count": count,
            "model": model_id,
            "spent_today_usd": round(spent_today(store_conn), 6),
            "daily_budget_usd": daily_budget_usd,
        }

    @app.get("/api/conversations")
    def conversations() -> list[dict[str, object]]:
        return [summary.model_dump() for summary in list_conversations(store_conn)]

    @app.get("/api/conversations/{conversation_id}")
    def conversation(conversation_id: int) -> dict[str, object]:
        summaries = [s for s in list_conversations(store_conn) if s.id == conversation_id]
        if not summaries:
            raise HTTPException(status_code=404, detail="No such conversation")
        return {
            "conversation": summaries[0].model_dump(),
            "turns": [turn.model_dump() for turn in load_turns(store_conn, conversation_id)],
        }

    @app.delete("/api/conversations/{conversation_id}", status_code=204)
    def remove_conversation(conversation_id: int) -> None:
        delete_conversation(store_conn, conversation_id)

    @app.post("/api/chat")
    def chat(request: ChatRequest) -> StreamingResponse:
        message = request.message.strip()
        if not message:
            raise HTTPException(status_code=422, detail="Ask me something about Pokémon!")

        conversation_id = request.conversation_id
        if conversation_id is None:
            conversation_id = create_conversation(store_conn, title_from(message))
            title = title_from(message)
        else:
            summaries = [s for s in list_conversations(store_conn) if s.id == conversation_id]
            if not summaries:
                raise HTTPException(status_code=404, detail="No such conversation")
            title = summaries[0].title

        async def body() -> AsyncIterator[str]:
            yield frame("start", {"conversation_id": conversation_id, "title": title})

            if is_over_budget(store_conn, daily_budget_usd):
                yield frame("limit", {"message": BUDGET_MESSAGE})
                yield frame("done", {"conversation_id": conversation_id})
                return

            recorder = TurnRecorder()
            history = load_history(store_conn, conversation_id)
            async for chunk in stream_turn(
                agent, PokedexDeps(conn=read_conn), message, history, recorder, usage_limits
            ):
                yield chunk

            if recorder.input_tokens or recorder.output_tokens:
                record_usage(
                    store_conn, model_id, recorder.input_tokens, recorder.output_tokens
                )

            if recorder.new_messages:
                save_turn(
                    store_conn,
                    conversation_id,
                    message,
                    recorder.text,
                    recorder.tool_events,
                    recorder.new_messages,
                )
            yield frame("done", {"conversation_id": conversation_id})

        return StreamingResponse(
            body(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # Mounted last, at the root, so it cannot shadow /api or /images.
    if web_dist is not None and web_dist.is_dir():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")

    return app
```

`api/app.py`:

```python
from __future__ import annotations

from pydantic_ai import UsageLimits

from api.main import create_app
from api.settings import get_settings

settings = get_settings()

app = create_app(
    db_path=settings.db_path,
    images_dir=settings.images_dir,
    model=settings.openai_model,
    web_dist=settings.web_dist,
    daily_budget_usd=settings.daily_budget_usd,
    usage_limits=UsageLimits(
        request_limit=settings.request_limit,
        tool_calls_limit=settings.tool_calls_limit,
        total_tokens_limit=settings.total_tokens_limit,
    ),
)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `uv run pytest tests/api/test_routes.py -v`
Expected: PASS, 9 passed

`FunctionModel` reports non-zero token usage, which is what makes `test_usage_is_recorded_after_a_turn` meaningful. If it reports zero on your version, assert on a row count in `usage_log` instead.

- [ ] **Step 5: Run the whole Python suite once**

Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 6: Start the server and check it by hand**

```bash
infisical run -- uv run fastapi dev api/app.py --port 8000
```

In a second terminal:

```bash
curl -s localhost:8000/api/health
curl -sN -X POST localhost:8000/api/chat -H 'content-type: application/json' \
  -d '{"message":"Which is faster, Pikachu or Onix?"}' | head -40
curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/images/official-artwork/25.png
```

Expected: a health payload with roughly 1,300 Pokémon; a live SSE stream with `start`, `tool`, `token`, and `done` frames; `200` for the artwork.

- [ ] **Step 7: Lint, format, and commit**

```bash
uv run ruff check --fix . && uv run ruff format .
git add api/main.py api/app.py tests/api/test_routes.py
git commit -m "feat: FastAPI app with SSE chat and conversation routes"
```

---

### Task 17: SvelteKit scaffold, Tailwind v4, and shared types

**Files:**
- Create: `web/` (via the `sv` CLI), `web/vite.config.ts`, `web/src/app.css`, `web/src/app.html`, `web/src/lib/types.ts`
- Test: `web/src/lib/types.test.ts`

**Interfaces:**
- Consumes: the JSON shapes produced by `api/models.py`
- Produces: `web/src/lib/types.ts` exporting `BaseStats`, `PokemonProfile`, `FindPokemonResult`, `TypeMatchup`, `MatchupReport`, `Comparison`, `EvolutionStep`, `EvolutionChain`, `SqlResult`, `ToolEvent`, `StoredTurn`, `ConversationSummary`, `SseEvent`, and `TYPE_COLORS`.

- [ ] **Step 1: Scaffold the app**

```bash
cd /home/jb/Developer/drew/pokemon_app
npx sv create web --template minimal --types ts --no-add-ons --install npm
cd web
npx sv add tailwindcss --no-preconditions
npx sv add vitest --no-preconditions
npm install
```

If `sv add` prompts, accept the defaults. Confirm `web/package.json` has `@tailwindcss/vite` and `vitest`, and that no `tailwind.config.ts` was created.

- [ ] **Step 2: Set the app name and proxy the API**

`web/package.json`: set `"name": "drews-pokemon-app"`.

`web/src/app.html`: set the title.

```html
<title>Drew's Pokémon App</title>
```

`web/vite.config.ts`:

```ts
import tailwindcss from '@tailwindcss/vite';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		proxy: {
			'/api': 'http://localhost:8000',
			'/images': 'http://localhost:8000'
		}
	},
	test: {
		include: ['src/**/*.test.ts'],
		environment: 'jsdom'
	}
});
```

```bash
npm install -D jsdom
```

- [ ] **Step 3: Configure Tailwind v4 theme in `web/src/app.css`**

```css
@import 'tailwindcss';

@theme inline {
	--color-ink: #1b1b1f;
	--color-paper: #fdfcf7;
	--color-panel: #ffffff;
	--color-accent: #d94f3d;
	--font-display: 'Trebuchet MS', 'Verdana', sans-serif;
	--radius-card: 1.25rem;
}

body {
	background: var(--color-paper);
	color: var(--color-ink);
}
```

- [ ] **Step 4: Write the failing test**

`web/src/lib/types.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { TYPE_COLORS, typeColor } from './types';

describe('type colors', () => {
	it('covers all eighteen Pokémon types', () => {
		expect(Object.keys(TYPE_COLORS)).toHaveLength(18);
	});

	it('looks up a colour by display name', () => {
		expect(typeColor('Electric')).toBe(TYPE_COLORS.Electric);
	});

	it('falls back for an unknown type', () => {
		expect(typeColor('Sparkle')).toBe('#9ca3af');
	});
});
```

- [ ] **Step 5: Run it and confirm it fails**

Run: `cd web && npx vitest run src/lib/types.test.ts`
Expected: FAIL, cannot resolve `./types`

- [ ] **Step 6: Implement `web/src/lib/types.ts`**

```ts
export interface BaseStats {
	hp: number;
	attack: number;
	defense: number;
	special_attack: number;
	special_defense: number;
	speed: number;
	total: number;
}

export interface PokemonProfile {
	id: number;
	name: string;
	slug: string;
	generation: number;
	types: string[];
	stats: BaseStats;
	height_m: number;
	weight_kg: number;
	abilities: string[];
	artwork_url: string;
	sprite_url: string;
	genus: string | null;
	flavor_text: string | null;
	is_legendary: boolean;
	is_mythical: boolean;
}

export interface FindPokemonResult {
	pokemon: PokemonProfile | null;
	candidates: string[];
}

export interface TypeMatchup {
	attacking: string;
	defending: string;
	multiplier: number;
	label: string;
}

export interface MatchupReport {
	attacking_types: string[];
	defending_types: string[];
	matchups: TypeMatchup[];
	combined_multiplier: number;
}

export interface Comparison {
	pokemon: PokemonProfile[];
	fastest: string;
	highest_total: string;
}

export interface EvolutionStep {
	from_name: string;
	to_name: string;
	trigger: string | null;
	min_level: number | null;
}

export interface EvolutionChain {
	chain_id: number;
	steps: EvolutionStep[];
}

export interface SqlResult {
	sql: string;
	columns: string[];
	rows: Record<string, unknown>[];
	row_count: number;
	truncated: boolean;
}

export type ToolName =
	| 'find_pokemon'
	| 'type_matchup'
	| 'compare'
	| 'evolution_chain'
	| 'run_sql';

export interface ToolEvent {
	tool_name: ToolName;
	args: Record<string, unknown>;
	result: unknown;
}

export interface StoredTurn {
	id: number;
	user_text: string;
	assistant_text: string;
	tool_events: ToolEvent[];
	created_at: string;
}

export interface ConversationSummary {
	id: number;
	title: string;
	created_at: string;
	updated_at: string;
	turn_count: number;
}

export type SseEvent =
	| { name: 'start'; data: { conversation_id: number; title: string } }
	| { name: 'token'; data: { text: string } }
	| { name: 'tool'; data: ToolEvent }
	| { name: 'limit'; data: { message: string } }
	| { name: 'done'; data: { conversation_id: number } }
	| { name: 'error'; data: { message: string } };

export const TYPE_COLORS: Record<string, string> = {
	Normal: '#9fa19f',
	Fighting: '#ff8000',
	Flying: '#81b9ef',
	Poison: '#9141cb',
	Ground: '#915121',
	Rock: '#afa981',
	Bug: '#91a119',
	Ghost: '#704170',
	Steel: '#60a1b8',
	Fire: '#e62829',
	Water: '#2980ef',
	Grass: '#3fa129',
	Electric: '#fac000',
	Psychic: '#ef4179',
	Ice: '#3dcef3',
	Dragon: '#5060e1',
	Dark: '#624d4e',
	Fairy: '#ef70ef'
};

export function typeColor(name: string): string {
	return TYPE_COLORS[name] ?? '#9ca3af';
}
```

- [ ] **Step 7: Run the test and confirm it passes**

Run: `cd web && npx vitest run src/lib/types.test.ts`
Expected: PASS, 3 passed

- [ ] **Step 8: Commit**

```bash
git add web
git commit -m "feat: SvelteKit scaffold with Tailwind v4 and shared types"
```

---

### Task 18: SSE client and chat state

**Files:**
- Create: `web/src/lib/sse.ts`, `web/src/lib/api.ts`, `web/src/lib/chat.svelte.ts`
- Test: `web/src/lib/sse.test.ts`, `web/src/lib/chat.test.ts`

**Interfaces:**
- Consumes: `web/src/lib/types.ts`
- Produces:
  - `parseFrames(buffer: string): { events: SseEvent[]; rest: string }` — pure, handles partial trailing frames.
  - `api.ts`: `listConversations()`, `loadConversation(id)`, `deleteConversation(id)`.
  - `chat.svelte.ts`: `createChat()` returning `{ messages, busy, error, conversationId, send(text), reset(), load(id) }` where `messages: ChatMessage[]` and `ChatMessage = { role: 'user' | 'assistant'; text: string; toolEvents: ToolEvent[] }`.

- [ ] **Step 1: Write the failing test for the frame parser**

`web/src/lib/sse.test.ts`:

```ts
import { describe, expect, it } from 'vitest';
import { parseFrames } from './sse';

describe('parseFrames', () => {
	it('parses a complete frame', () => {
		const { events, rest } = parseFrames('event: token\ndata: {"text":"hi"}\n\n');
		expect(events).toEqual([{ name: 'token', data: { text: 'hi' } }]);
		expect(rest).toBe('');
	});

	it('parses several frames at once', () => {
		const raw =
			'event: token\ndata: {"text":"a"}\n\nevent: token\ndata: {"text":"b"}\n\n';
		expect(parseFrames(raw).events).toHaveLength(2);
	});

	it('keeps a partial trailing frame in rest', () => {
		const { events, rest } = parseFrames('event: token\ndata: {"text":"a"}\n\nevent: tok');
		expect(events).toHaveLength(1);
		expect(rest).toBe('event: tok');
	});

	it('skips frames with unparseable data', () => {
		expect(parseFrames('event: token\ndata: not json\n\n').events).toEqual([]);
	});
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd web && npx vitest run src/lib/sse.test.ts`
Expected: FAIL, cannot resolve `./sse`

- [ ] **Step 3: Implement `web/src/lib/sse.ts`**

```ts
import type { SseEvent } from './types';

export function parseFrames(buffer: string): { events: SseEvent[]; rest: string } {
	const parts = buffer.split('\n\n');
	const rest = parts.pop() ?? '';
	const events: SseEvent[] = [];

	for (const block of parts) {
		const lines = block.split('\n');
		const nameLine = lines.find((l) => l.startsWith('event: '));
		const dataLine = lines.find((l) => l.startsWith('data: '));
		if (!nameLine || !dataLine) continue;
		try {
			events.push({
				name: nameLine.slice(7).trim(),
				data: JSON.parse(dataLine.slice(6))
			} as SseEvent);
		} catch {
			// A malformed frame is dropped rather than killing the stream.
		}
	}

	return { events, rest };
}

export async function* streamChat(
	message: string,
	conversationId: number | null,
	signal?: AbortSignal
): AsyncGenerator<SseEvent> {
	const response = await fetch('/api/chat', {
		method: 'POST',
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify({ message, conversation_id: conversationId }),
		signal
	});

	if (!response.ok || !response.body) {
		throw new Error(`The Pokédex is not answering (HTTP ${response.status}).`);
	}

	const reader = response.body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';

	while (true) {
		const { done, value } = await reader.read();
		if (done) break;
		buffer += decoder.decode(value, { stream: true });
		const { events, rest } = parseFrames(buffer);
		buffer = rest;
		for (const event of events) yield event;
	}
}
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `cd web && npx vitest run src/lib/sse.test.ts`
Expected: PASS, 4 passed

- [ ] **Step 5: Write the failing test for chat state**

`web/src/lib/chat.test.ts`:

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createChat } from './chat.svelte';

function sseResponse(frames: string[]): Response {
	const stream = new ReadableStream({
		start(controller) {
			const encoder = new TextEncoder();
			for (const frame of frames) controller.enqueue(encoder.encode(frame));
			controller.close();
		}
	});
	return new Response(stream, { status: 200 });
}

const FRAMES = [
	'event: start\ndata: {"conversation_id":7,"title":"Who is Pikachu?"}\n\n',
	'event: tool\ndata: {"tool_name":"find_pokemon","args":{"name_or_id":"pikachu"},"result":{"pokemon":{"name":"Pikachu"}}}\n\n',
	'event: token\ndata: {"text":"Pikachu "}\n\n',
	'event: token\ndata: {"text":"is quick!"}\n\n',
	'event: done\ndata: {"conversation_id":7}\n\n'
];

describe('createChat', () => {
	beforeEach(() => vi.restoreAllMocks());

	it('appends the user message immediately', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(FRAMES)));
		const chat = createChat();
		await chat.send('Who is Pikachu?');
		expect(chat.messages[0].role).toBe('user');
		expect(chat.messages[0].text).toBe('Who is Pikachu?');
	});

	it('accumulates tokens and tool events onto the assistant message', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(FRAMES)));
		const chat = createChat();
		await chat.send('Who is Pikachu?');
		const assistant = chat.messages[1];
		expect(assistant.role).toBe('assistant');
		expect(assistant.text).toBe('Pikachu is quick!');
		expect(assistant.toolEvents[0].tool_name).toBe('find_pokemon');
		expect(chat.conversationId).toBe(7);
		expect(chat.busy).toBe(false);
	});

	it('shows a limit frame as the answer, not an error', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(
				sseResponse([
					'event: start\ndata: {"conversation_id":1,"title":"hi"}\n\n',
					'event: limit\ndata: {"message":"That\'s all the Pokémon questions for today, Drew. Come back tomorrow!"}\n\n',
					'event: done\ndata: {"conversation_id":1}\n\n'
				])
			)
		);
		const chat = createChat();
		await chat.send('one more');
		expect(chat.messages[1].text).toContain('Come back tomorrow');
		expect(chat.error).toBeNull();
	});

	it('surfaces an error frame', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(
				sseResponse(['event: error\ndata: {"message":"provider exploded"}\n\n'])
			)
		);
		const chat = createChat();
		await chat.send('hi');
		expect(chat.error).toContain('provider exploded');
		expect(chat.busy).toBe(false);
	});

	it('ignores an empty message', async () => {
		const fetchMock = vi.fn();
		vi.stubGlobal('fetch', fetchMock);
		const chat = createChat();
		await chat.send('   ');
		expect(fetchMock).not.toHaveBeenCalled();
		expect(chat.messages).toHaveLength(0);
	});
});
```

- [ ] **Step 6: Run it and confirm it fails**

Run: `cd web && npx vitest run src/lib/chat.test.ts`
Expected: FAIL, cannot resolve `./chat.svelte`

- [ ] **Step 7: Implement `web/src/lib/api.ts`**

```ts
import type { ConversationSummary, StoredTurn } from './types';

export async function listConversations(): Promise<ConversationSummary[]> {
	const response = await fetch('/api/conversations');
	if (!response.ok) return [];
	return response.json();
}

export async function loadConversation(
	id: number
): Promise<{ conversation: ConversationSummary; turns: StoredTurn[] } | null> {
	const response = await fetch(`/api/conversations/${id}`);
	if (!response.ok) return null;
	return response.json();
}

export async function deleteConversation(id: number): Promise<void> {
	await fetch(`/api/conversations/${id}`, { method: 'DELETE' });
}
```

- [ ] **Step 8: Implement `web/src/lib/chat.svelte.ts`**

```ts
import { loadConversation } from './api';
import { streamChat } from './sse';
import type { ToolEvent } from './types';

export interface ChatMessage {
	role: 'user' | 'assistant';
	text: string;
	toolEvents: ToolEvent[];
}

export function createChat() {
	let messages = $state<ChatMessage[]>([]);
	let busy = $state(false);
	let error = $state<string | null>(null);
	let conversationId = $state<number | null>(null);

	async function send(text: string): Promise<void> {
		const question = text.trim();
		if (!question || busy) return;

		error = null;
		busy = true;
		messages.push({ role: 'user', text: question, toolEvents: [] });

		const assistant: ChatMessage = { role: 'assistant', text: '', toolEvents: [] };
		messages.push(assistant);

		try {
			for await (const event of streamChat(question, conversationId)) {
				if (event.name === 'start') {
					conversationId = event.data.conversation_id;
				} else if (event.name === 'token') {
					assistant.text += event.data.text;
				} else if (event.name === 'tool') {
					assistant.toolEvents.push(event.data);
				} else if (event.name === 'limit') {
					// Budget or loop cap. Drew sees a sentence, not an error banner.
					assistant.text = event.data.message;
				} else if (event.name === 'error') {
					error = event.data.message;
				}
			}
		} catch (cause) {
			error = cause instanceof Error ? cause.message : String(cause);
		} finally {
			busy = false;
		}
	}

	function reset(): void {
		messages = [];
		conversationId = null;
		error = null;
	}

	async function load(id: number): Promise<void> {
		const detail = await loadConversation(id);
		if (!detail) return;
		conversationId = id;
		error = null;
		messages = detail.turns.flatMap((turn) => [
			{ role: 'user' as const, text: turn.user_text, toolEvents: [] },
			{ role: 'assistant' as const, text: turn.assistant_text, toolEvents: turn.tool_events }
		]);
	}

	return {
		get messages() {
			return messages;
		},
		get busy() {
			return busy;
		},
		get error() {
			return error;
		},
		get conversationId() {
			return conversationId;
		},
		send,
		reset,
		load
	};
}
```

- [ ] **Step 9: Run the tests and confirm they pass**

Run: `cd web && npx vitest run src/lib/chat.test.ts`
Expected: PASS, 5 passed

If Vitest reports that runes are unavailable in a `.ts` file, confirm the file is named `chat.svelte.ts` and that `vitest` is running through the SvelteKit Vite config, which applies the Svelte compiler to `.svelte.ts` files.

- [ ] **Step 10: Commit**

```bash
git add web/src/lib
git commit -m "feat: SSE client and chat state"
```

---

### Task 19: Pokémon card

**Files:**
- Create: `web/src/lib/components/TypeBadge.svelte`, `web/src/lib/components/StatBars.svelte`, `web/src/lib/components/PokemonCard.svelte`
- Test: `web/src/lib/components/PokemonCard.test.ts`

**Interfaces:**
- Consumes: `PokemonProfile`, `typeColor`
- Produces: `<PokemonCard pokemon={profile} />`, `<TypeBadge name="Electric" />`, `<StatBars stats={profile.stats} />`. `STAT_MAX = 255` is the bar scale.

- [ ] **Step 1: Install the component testing library**

```bash
cd web && npm install -D @testing-library/svelte @testing-library/jest-dom
```

Add `web/vitest-setup.ts`:

```ts
import '@testing-library/jest-dom/vitest';
```

and in `web/vite.config.ts` add `setupFiles: ['./vitest-setup.ts']` inside `test`.

- [ ] **Step 2: Write the failing test**

`web/src/lib/components/PokemonCard.test.ts`:

```ts
import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import PokemonCard from './PokemonCard.svelte';
import type { PokemonProfile } from '../types';

const pikachu: PokemonProfile = {
	id: 25,
	name: 'Pikachu',
	slug: 'pikachu',
	generation: 1,
	types: ['Electric'],
	stats: {
		hp: 35,
		attack: 55,
		defense: 40,
		special_attack: 50,
		special_defense: 50,
		speed: 90,
		total: 320
	},
	height_m: 0.4,
	weight_kg: 6,
	abilities: ['Static'],
	artwork_url: '/images/official-artwork/25.png',
	sprite_url: '/images/front-default/25.png',
	genus: 'Mouse Pokémon',
	flavor_text: 'It raises its tail to check its surroundings.',
	is_legendary: false,
	is_mythical: false
};

describe('PokemonCard', () => {
	it('shows the name, number, and genus', () => {
		render(PokemonCard, { pokemon: pikachu });
		expect(screen.getByText('Pikachu')).toBeInTheDocument();
		expect(screen.getByText('#025')).toBeInTheDocument();
		expect(screen.getByText('Mouse Pokémon')).toBeInTheDocument();
	});

	it('shows the artwork with a useful alt text', () => {
		render(PokemonCard, { pokemon: pikachu });
		const image = screen.getByAltText('Pikachu');
		expect(image).toHaveAttribute('src', '/images/official-artwork/25.png');
	});

	it('shows every type as a badge', () => {
		render(PokemonCard, { pokemon: { ...pikachu, types: ['Fire', 'Flying'] } });
		expect(screen.getByText('Fire')).toBeInTheDocument();
		expect(screen.getByText('Flying')).toBeInTheDocument();
	});

	it('shows kid-friendly stat labels and the total', () => {
		render(PokemonCard, { pokemon: pikachu });
		expect(screen.getByText('Health')).toBeInTheDocument();
		expect(screen.getByText('Speed')).toBeInTheDocument();
		expect(screen.getByText('320')).toBeInTheDocument();
	});

	it('shows height and weight in kid units', () => {
		render(PokemonCard, { pokemon: pikachu });
		expect(screen.getByText('0.4 m')).toBeInTheDocument();
		expect(screen.getByText('6 kg')).toBeInTheDocument();
	});
});
```

- [ ] **Step 3: Run it and confirm it fails**

Run: `cd web && npx vitest run src/lib/components/PokemonCard.test.ts`
Expected: FAIL, cannot resolve `./PokemonCard.svelte`

- [ ] **Step 4: Implement `TypeBadge.svelte`**

```svelte
<script lang="ts">
	import { typeColor } from '../types';

	let { name }: { name: string } = $props();
</script>

<span
	class="rounded-full px-3 py-1 text-sm font-bold text-white shadow-sm"
	style="background-color: {typeColor(name)}"
>
	{name}
</span>
```

- [ ] **Step 5: Implement `StatBars.svelte`**

```svelte
<script lang="ts">
	import type { BaseStats } from '../types';

	let { stats }: { stats: BaseStats } = $props();

	const STAT_MAX = 255;

	const rows = $derived([
		{ label: 'Health', value: stats.hp },
		{ label: 'Attack', value: stats.attack },
		{ label: 'Defense', value: stats.defense },
		{ label: 'Special Attack', value: stats.special_attack },
		{ label: 'Special Defense', value: stats.special_defense },
		{ label: 'Speed', value: stats.speed }
	]);
</script>

<div class="space-y-1.5">
	<p class="text-xs text-ink/60">
		Base stats are how strong this Pokémon is naturally, before any training.
	</p>
	{#each rows as row (row.label)}
		<div class="flex items-center gap-2">
			<span class="w-32 shrink-0 text-sm">{row.label}</span>
			<div class="h-3 flex-1 overflow-hidden rounded-full bg-ink/10">
				<div
					class="h-full rounded-full bg-accent"
					style="width: {Math.round((row.value / STAT_MAX) * 100)}%"
				></div>
			</div>
			<span class="w-10 shrink-0 text-right text-sm tabular-nums">{row.value}</span>
		</div>
	{/each}
	<div class="flex items-center gap-2 pt-1 font-bold">
		<span class="w-32 shrink-0 text-sm">Total</span>
		<span class="flex-1"></span>
		<span class="w-10 shrink-0 text-right text-sm tabular-nums">{stats.total}</span>
	</div>
</div>
```

- [ ] **Step 6: Implement `PokemonCard.svelte`**

```svelte
<script lang="ts">
	import type { PokemonProfile } from '../types';
	import StatBars from './StatBars.svelte';
	import TypeBadge from './TypeBadge.svelte';

	let { pokemon }: { pokemon: PokemonProfile } = $props();

	const number = $derived(`#${String(pokemon.id).padStart(3, '0')}`);
</script>

<article class="rounded-card bg-panel p-5 shadow-md ring-1 ring-ink/5">
	<div class="flex flex-col gap-5 sm:flex-row">
		<img
			src={pokemon.artwork_url}
			alt={pokemon.name}
			loading="lazy"
			class="mx-auto h-56 w-56 shrink-0 object-contain"
		/>
		<div class="flex-1 space-y-3">
			<header class="space-y-1">
				<div class="flex items-baseline gap-2">
					<h3 class="font-display text-3xl font-bold">{pokemon.name}</h3>
					<span class="text-lg text-ink/50 tabular-nums">{number}</span>
				</div>
				{#if pokemon.genus}
					<p class="text-sm text-ink/60">{pokemon.genus}</p>
				{/if}
			</header>

			<div class="flex flex-wrap gap-2">
				{#each pokemon.types as type (type)}
					<TypeBadge name={type} />
				{/each}
			</div>

			<dl class="flex gap-6 text-sm">
				<div><dt class="text-ink/60">Height</dt><dd>{pokemon.height_m} m</dd></div>
				<div><dt class="text-ink/60">Weight</dt><dd>{pokemon.weight_kg} kg</dd></div>
				<div>
					<dt class="text-ink/60">Abilities</dt>
					<dd>{pokemon.abilities.join(', ') || '—'}</dd>
				</div>
			</dl>

			<StatBars stats={pokemon.stats} />

			{#if pokemon.flavor_text}
				<p class="border-l-4 border-accent/40 pl-3 text-sm italic text-ink/70">
					{pokemon.flavor_text}
				</p>
			{/if}
		</div>
	</div>
</article>
```

- [ ] **Step 7: Run the tests and confirm they pass**

Run: `cd web && npx vitest run src/lib/components/PokemonCard.test.ts`
Expected: PASS, 5 passed

- [ ] **Step 8: Commit**

```bash
git add web/src/lib/components web/vitest-setup.ts web/vite.config.ts web/package.json
git commit -m "feat: Pokemon card, type badges, and stat bars"
```

---

### Task 20: Remaining tool renderers

**Files:**
- Create: `web/src/lib/components/ComparisonTable.svelte`, `TypeChart.svelte`, `EvolutionLine.svelte`, `SqlTable.svelte`, `ToolChip.svelte`, `ToolResult.svelte`
- Test: `web/src/lib/components/ToolResult.test.ts`

**Interfaces:**
- Consumes: every model in `types.ts`, `PokemonCard`
- Produces: `<ToolResult event={toolEvent} />`, which switches on `event.tool_name` and renders the right component. Unknown or empty results render nothing.

- [ ] **Step 1: Write the failing test**

`web/src/lib/components/ToolResult.test.ts`:

```ts
import { render, screen } from '@testing-library/svelte';
import { describe, expect, it } from 'vitest';
import ToolResult from './ToolResult.svelte';
import type { ToolEvent } from '../types';

const profile = {
	id: 25, name: 'Pikachu', slug: 'pikachu', generation: 1, types: ['Electric'],
	stats: { hp: 35, attack: 55, defense: 40, special_attack: 50, special_defense: 50, speed: 90, total: 320 },
	height_m: 0.4, weight_kg: 6, abilities: ['Static'],
	artwork_url: '/images/official-artwork/25.png', sprite_url: '/images/front-default/25.png',
	genus: 'Mouse Pokémon', flavor_text: null, is_legendary: false, is_mythical: false
};

function event(tool_name: ToolEvent['tool_name'], result: unknown): ToolEvent {
	return { tool_name, args: {}, result };
}

describe('ToolResult', () => {
	it('renders a card for find_pokemon', () => {
		render(ToolResult, { event: event('find_pokemon', { pokemon: profile, candidates: [] }) });
		expect(screen.getByText('Pikachu')).toBeInTheDocument();
	});

	it('renders nothing for find_pokemon with no match', () => {
		const { container } = render(ToolResult, {
			event: event('find_pokemon', { pokemon: null, candidates: ['pikachu'] })
		});
		expect(container.textContent?.trim()).toBe('');
	});

	it('renders a comparison table', () => {
		render(ToolResult, {
			event: event('compare', { pokemon: [profile], fastest: 'Pikachu', highest_total: 'Pikachu' })
		});
		expect(screen.getByText('Fastest')).toBeInTheDocument();
	});

	it('renders a matchup with its plain-language label', () => {
		render(ToolResult, {
			event: event('type_matchup', {
				attacking_types: ['Water'],
				defending_types: ['Fire'],
				matchups: [{ attacking: 'Water', defending: 'Fire', multiplier: 2, label: 'super effective' }],
				combined_multiplier: 2
			})
		});
		expect(screen.getByText('super effective')).toBeInTheDocument();
		expect(screen.getByText('2×')).toBeInTheDocument();
	});

	it('renders an evolution line', () => {
		render(ToolResult, {
			event: event('evolution_chain', {
				chain_id: 10,
				steps: [{ from_name: 'Pikachu', to_name: 'Raichu', trigger: 'use-item', min_level: null }]
			})
		});
		expect(screen.getByText('Raichu')).toBeInTheDocument();
	});

	it('renders a SQL result table', () => {
		render(ToolResult, {
			event: event('run_sql', {
				sql: 'SELECT name FROM v_pokemon LIMIT 200',
				columns: ['name'],
				rows: [{ name: 'Pikachu' }],
				row_count: 1,
				truncated: false
			})
		});
		expect(screen.getByText('name')).toBeInTheDocument();
		expect(screen.getByText('Pikachu')).toBeInTheDocument();
	});
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd web && npx vitest run src/lib/components/ToolResult.test.ts`
Expected: FAIL, cannot resolve `./ToolResult.svelte`

- [ ] **Step 3: Implement `ComparisonTable.svelte`**

```svelte
<script lang="ts">
	import type { Comparison } from '../types';
	import TypeBadge from './TypeBadge.svelte';

	let { comparison }: { comparison: Comparison } = $props();

	const rows = $derived([
		{ label: 'Health', key: 'hp' as const },
		{ label: 'Attack', key: 'attack' as const },
		{ label: 'Defense', key: 'defense' as const },
		{ label: 'Special Attack', key: 'special_attack' as const },
		{ label: 'Special Defense', key: 'special_defense' as const },
		{ label: 'Speed', key: 'speed' as const },
		{ label: 'Total', key: 'total' as const }
	]);

	function best(key: (typeof rows)[number]['key']): number {
		return Math.max(...comparison.pokemon.map((p) => p.stats[key]));
	}
</script>

<div class="overflow-x-auto rounded-card bg-panel p-4 shadow-md ring-1 ring-ink/5">
	<table class="w-full text-sm">
		<thead>
			<tr>
				<th class="p-2 text-left"></th>
				{#each comparison.pokemon as p (p.id)}
					<th class="p-2 text-center">
						<img src={p.sprite_url} alt={p.name} class="mx-auto h-16 w-16" />
						<div class="font-bold">{p.name}</div>
						<div class="mt-1 flex justify-center gap-1">
							{#each p.types as type (type)}<TypeBadge name={type} />{/each}
						</div>
					</th>
				{/each}
			</tr>
		</thead>
		<tbody>
			{#each rows as row (row.key)}
				<tr class="border-t border-ink/10">
					<td class="p-2 text-ink/70">{row.label}</td>
					{#each comparison.pokemon as p (p.id)}
						<td
							class="p-2 text-center tabular-nums"
							class:font-bold={p.stats[row.key] === best(row.key)}
							class:text-accent={p.stats[row.key] === best(row.key)}
						>
							{p.stats[row.key]}
						</td>
					{/each}
				</tr>
			{/each}
		</tbody>
	</table>
	<p class="mt-3 text-sm text-ink/70">
		<span class="font-bold">Fastest</span>: {comparison.fastest} ·
		<span class="font-bold">Highest total</span>: {comparison.highest_total}
	</p>
</div>
```

- [ ] **Step 4: Implement `TypeChart.svelte`**

```svelte
<script lang="ts">
	import type { MatchupReport } from '../types';
	import TypeBadge from './TypeBadge.svelte';

	let { report }: { report: MatchupReport } = $props();
</script>

<div class="rounded-card bg-panel p-4 shadow-md ring-1 ring-ink/5">
	<div class="flex flex-wrap items-center gap-2">
		{#each report.attacking_types as type (type)}<TypeBadge name={type} />{/each}
		<span class="text-ink/50">attacking</span>
		{#each report.defending_types as type (type)}<TypeBadge name={type} />{/each}
	</div>
	<p class="mt-3 text-2xl font-bold text-accent">{report.combined_multiplier}×</p>
	<ul class="mt-2 space-y-1 text-sm">
		{#each report.matchups as matchup (matchup.defending)}
			<li>
				<span class="font-medium">vs {matchup.defending}</span>
				<span class="text-ink/60"> — {matchup.label}</span>
			</li>
		{/each}
	</ul>
</div>
```

- [ ] **Step 5: Implement `EvolutionLine.svelte`**

```svelte
<script lang="ts">
	import type { EvolutionChain } from '../types';

	let { chain }: { chain: EvolutionChain } = $props();

	function how(trigger: string | null, level: number | null): string {
		if (level) return `at level ${level}`;
		if (trigger === 'use-item') return 'with an item';
		if (trigger === 'trade') return 'by trading';
		return trigger ? trigger.replace(/-/g, ' ') : '';
	}
</script>

<div class="rounded-card bg-panel p-4 shadow-md ring-1 ring-ink/5">
	<ul class="space-y-2">
		{#each chain.steps as step (step.from_name + step.to_name)}
			<li class="flex flex-wrap items-center gap-2 text-sm">
				<span class="font-bold">{step.from_name}</span>
				<span class="text-accent">→</span>
				<span class="font-bold">{step.to_name}</span>
				<span class="text-ink/60">{how(step.trigger, step.min_level)}</span>
			</li>
		{/each}
	</ul>
</div>
```

- [ ] **Step 6: Implement `SqlTable.svelte`**

```svelte
<script lang="ts">
	import type { SqlResult } from '../types';

	let { result }: { result: SqlResult } = $props();
</script>

<div class="overflow-x-auto rounded-card bg-panel p-4 shadow-md ring-1 ring-ink/5">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-ink/10">
				{#each result.columns as column (column)}
					<th class="p-2 text-left font-bold">{column}</th>
				{/each}
			</tr>
		</thead>
		<tbody>
			{#each result.rows as row, index (index)}
				<tr class="border-b border-ink/5">
					{#each result.columns as column (column)}
						<td class="p-2">{row[column]}</td>
					{/each}
				</tr>
			{/each}
		</tbody>
	</table>
	{#if result.truncated}
		<p class="mt-2 text-xs text-ink/60">Showing the first {result.row_count} results.</p>
	{/if}
</div>
```

- [ ] **Step 7: Implement `ToolChip.svelte`**

```svelte
<script lang="ts">
	import type { SqlResult, ToolEvent } from '../types';

	let { event }: { event: ToolEvent } = $props();

	const LABELS: Record<ToolEvent['tool_name'], string> = {
		find_pokemon: 'looked it up in the Pokédex',
		type_matchup: 'checked the type chart',
		compare: 'compared them side by side',
		evolution_chain: 'traced the evolution line',
		run_sql: 'searched the whole Pokédex'
	};

	let open = $state(false);
	const sql = $derived(
		event.tool_name === 'run_sql' ? (event.result as SqlResult)?.sql : null
	);
</script>

<div class="text-xs">
	<button
		type="button"
		class="rounded-full bg-ink/5 px-3 py-1 text-ink/60 hover:bg-ink/10"
		onclick={() => (open = !open)}
	>
		{LABELS[event.tool_name] ?? event.tool_name}
	</button>
	{#if open}
		<pre class="mt-1 overflow-x-auto rounded-lg bg-ink/5 p-2 text-[11px]">{sql ??
				JSON.stringify(event.args, null, 2)}</pre>
	{/if}
</div>
```

- [ ] **Step 8: Implement `ToolResult.svelte`**

```svelte
<script lang="ts">
	import type {
		Comparison,
		EvolutionChain,
		FindPokemonResult,
		MatchupReport,
		SqlResult,
		ToolEvent
	} from '../types';
	import ComparisonTable from './ComparisonTable.svelte';
	import EvolutionLine from './EvolutionLine.svelte';
	import PokemonCard from './PokemonCard.svelte';
	import SqlTable from './SqlTable.svelte';
	import TypeChart from './TypeChart.svelte';

	let { event }: { event: ToolEvent } = $props();
</script>

{#if event.tool_name === 'find_pokemon' && (event.result as FindPokemonResult)?.pokemon}
	<PokemonCard pokemon={(event.result as FindPokemonResult).pokemon!} />
{:else if event.tool_name === 'compare' && (event.result as Comparison)?.pokemon?.length}
	<ComparisonTable comparison={event.result as Comparison} />
{:else if event.tool_name === 'type_matchup' && event.result}
	<TypeChart report={event.result as MatchupReport} />
{:else if event.tool_name === 'evolution_chain' && (event.result as EvolutionChain)?.steps?.length}
	<EvolutionLine chain={event.result as EvolutionChain} />
{:else if event.tool_name === 'run_sql' && (event.result as SqlResult)?.row_count}
	<SqlTable result={event.result as SqlResult} />
{/if}
```

- [ ] **Step 9: Run the tests and confirm they pass**

Run: `cd web && npx vitest run src/lib/components/ToolResult.test.ts`
Expected: PASS, 6 passed

- [ ] **Step 10: Commit**

```bash
git add web/src/lib/components
git commit -m "feat: comparison, matchup, evolution, and SQL renderers"
```

---

### Task 21: Chat screen

**Files:**
- Create: `web/src/routes/+layout.svelte`, `web/src/routes/+page.svelte`, `web/src/lib/components/ChatMessage.svelte`, `EmptyState.svelte`, `Composer.svelte`, `Sidebar.svelte`
- Test: `web/src/lib/components/EmptyState.test.ts`

**Interfaces:**
- Consumes: `createChat`, `ToolResult`, `ToolChip`, `listConversations`, `deleteConversation`
- Produces: the running app. `EmptyState` takes an `onpick: (question: string) => void` callback and offers four starter questions, one per question type.

- [ ] **Step 1: Write the failing test**

`web/src/lib/components/EmptyState.test.ts`:

```ts
import { render, screen } from '@testing-library/svelte';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import EmptyState from './EmptyState.svelte';
import { STARTERS } from './EmptyState.svelte';

describe('EmptyState', () => {
	it('greets Drew by name', () => {
		render(EmptyState, { onpick: () => {} });
		expect(screen.getByText(/Hey Drew/)).toBeInTheDocument();
	});

	it('offers four starter questions', () => {
		render(EmptyState, { onpick: () => {} });
		expect(screen.getAllByRole('button')).toHaveLength(4);
	});

	it('calls onpick with the question that was clicked', async () => {
		const onpick = vi.fn();
		render(EmptyState, { onpick });
		await userEvent.click(screen.getAllByRole('button')[0]);
		expect(onpick).toHaveBeenCalledWith(STARTERS[0]);
	});
});
```

```bash
cd web && npm install -D @testing-library/user-event
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd web && npx vitest run src/lib/components/EmptyState.test.ts`
Expected: FAIL, cannot resolve `./EmptyState.svelte`

- [ ] **Step 3: Implement `EmptyState.svelte`**

```svelte
<script lang="ts" module>
	export const STARTERS = [
		'What are Gengar‘s abilities?',
		'Which Water type under 10 kg is the fastest?',
		'Would Pikachu beat Onix?',
		'Build me a balanced team around Charizard.'
	];
</script>

<script lang="ts">
	let { onpick }: { onpick: (question: string) => void } = $props();
</script>

<div class="mx-auto max-w-2xl py-16 text-center">
	<h2 class="font-display text-3xl font-bold">Hey Drew, ask me anything about Pokémon.</h2>
	<p class="mt-2 text-ink/60">
		I have every Pokémon in here. Try one of these to get started.
	</p>
	<div class="mt-6 grid gap-3 sm:grid-cols-2">
		{#each STARTERS as starter (starter)}
			<button
				type="button"
				class="rounded-card bg-panel p-4 text-left text-sm shadow-sm ring-1 ring-ink/5 hover:ring-accent"
				onclick={() => onpick(starter)}
			>
				{starter}
			</button>
		{/each}
	</div>
</div>
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `cd web && npx vitest run src/lib/components/EmptyState.test.ts`
Expected: PASS, 3 passed

- [ ] **Step 5: Implement `ChatMessage.svelte`**

```svelte
<script lang="ts">
	import type { ChatMessage } from '../chat.svelte';
	import ToolChip from './ToolChip.svelte';
	import ToolResult from './ToolResult.svelte';

	let { message }: { message: ChatMessage } = $props();
</script>

{#if message.role === 'user'}
	<div class="flex justify-end">
		<p class="max-w-[80%] rounded-card bg-accent px-4 py-2 text-white">{message.text}</p>
	</div>
{:else}
	<div class="space-y-3">
		{#if message.toolEvents.length}
			<div class="flex flex-wrap gap-2">
				{#each message.toolEvents as event, index (index)}
					<ToolChip {event} />
				{/each}
			</div>
		{/if}
		{#if message.text}
			<p class="whitespace-pre-wrap leading-relaxed">{message.text}</p>
		{/if}
		{#each message.toolEvents as event, index (index)}
			<ToolResult {event} />
		{/each}
	</div>
{/if}
```

- [ ] **Step 6: Implement `Composer.svelte`**

```svelte
<script lang="ts">
	let {
		busy,
		onsend
	}: { busy: boolean; onsend: (text: string) => void } = $props();

	let text = $state('');

	function submit(submitEvent: SubmitEvent) {
		submitEvent.preventDefault();
		if (!text.trim() || busy) return;
		onsend(text);
		text = '';
	}
</script>

<form class="flex gap-2" onsubmit={submit}>
	<input
		bind:value={text}
		placeholder="Ask about any Pokémon…"
		aria-label="Ask about any Pokémon"
		class="flex-1 rounded-full bg-panel px-5 py-3 shadow-sm ring-1 ring-ink/10 outline-none focus:ring-accent"
	/>
	<button
		type="submit"
		disabled={busy || !text.trim()}
		class="rounded-full bg-accent px-6 py-3 font-bold text-white disabled:opacity-40"
	>
		{busy ? 'Thinking…' : 'Ask'}
	</button>
</form>
```

- [ ] **Step 7: Implement `Sidebar.svelte`**

```svelte
<script lang="ts">
	import type { ConversationSummary } from '../types';

	let {
		conversations,
		activeId,
		onselect,
		onnew,
		ondelete
	}: {
		conversations: ConversationSummary[];
		activeId: number | null;
		onselect: (id: number) => void;
		onnew: () => void;
		ondelete: (id: number) => void;
	} = $props();
</script>

<aside class="hidden w-64 shrink-0 border-r border-ink/10 p-4 lg:block">
	<button
		type="button"
		class="w-full rounded-full bg-accent px-4 py-2 text-sm font-bold text-white"
		onclick={onnew}
	>
		New question
	</button>
	<ul class="mt-4 space-y-1">
		{#each conversations as conversation (conversation.id)}
			<li class="group flex items-center gap-1">
				<button
					type="button"
					class="flex-1 truncate rounded-lg px-3 py-2 text-left text-sm hover:bg-ink/5"
					class:bg-ink-5={conversation.id === activeId}
					onclick={() => onselect(conversation.id)}
				>
					{conversation.title}
				</button>
				<button
					type="button"
					aria-label="Delete {conversation.title}"
					class="px-2 text-ink/30 opacity-0 group-hover:opacity-100 hover:text-accent"
					onclick={() => ondelete(conversation.id)}
				>
					×
				</button>
			</li>
		{/each}
	</ul>
</aside>
```

- [ ] **Step 8: Implement `+layout.svelte`**

```svelte
<script lang="ts">
	import '../app.css';

	let { children } = $props();
</script>

<div class="flex min-h-screen flex-col">
	<header class="border-b border-ink/10 px-6 py-4">
		<h1 class="font-display text-2xl font-bold">Drew's Pokémon App</h1>
	</header>
	{@render children()}
</div>
```

- [ ] **Step 9: Implement `+page.svelte`**

```svelte
<script lang="ts">
	import { deleteConversation, listConversations } from '$lib/api';
	import { createChat } from '$lib/chat.svelte';
	import ChatMessage from '$lib/components/ChatMessage.svelte';
	import Composer from '$lib/components/Composer.svelte';
	import EmptyState from '$lib/components/EmptyState.svelte';
	import Sidebar from '$lib/components/Sidebar.svelte';
	import type { ConversationSummary } from '$lib/types';

	const chat = createChat();
	let conversations = $state<ConversationSummary[]>([]);

	$effect(() => {
		void refresh();
	});

	async function refresh() {
		conversations = await listConversations();
	}

	async function send(text: string) {
		await chat.send(text);
		await refresh();
	}

	async function remove(id: number) {
		await deleteConversation(id);
		if (chat.conversationId === id) chat.reset();
		await refresh();
	}
</script>

<div class="flex flex-1">
	<Sidebar
		{conversations}
		activeId={chat.conversationId}
		onselect={(id) => chat.load(id)}
		onnew={() => chat.reset()}
		ondelete={remove}
	/>

	<main class="mx-auto flex w-full max-w-3xl flex-col gap-6 px-4 py-6">
		<div class="flex-1 space-y-6">
			{#if chat.messages.length === 0}
				<EmptyState onpick={send} />
			{:else}
				{#each chat.messages as message, index (index)}
					<ChatMessage {message} />
				{/each}
			{/if}

			{#if chat.error}
				<p class="rounded-card bg-accent/10 p-4 text-sm text-accent">
					Something went wrong: {chat.error}
				</p>
			{/if}
		</div>

		<div class="sticky bottom-4">
			<Composer busy={chat.busy} onsend={send} />
		</div>
	</main>
</div>
```

- [ ] **Step 10: Run the full frontend suite and the type check**

```bash
cd web && npx vitest run && npm run check
```

Expected: all tests pass, no TypeScript errors.

- [ ] **Step 11: Commit**

```bash
git add web/src
git commit -m "feat: chat screen with sidebar and starter questions"
```

---

### Task 21b: Single-process deploy on the Minisforum

**Files:**
- Create: `deploy/drews-pokemon-app.service`, `deploy/install.sh`
- Modify: `web/svelte.config.js` (static adapter), `web/src/routes/+layout.ts`

**Interfaces:**
- Consumes: `api.app.app`, `settings.web_dist`
- Produces: a service that starts on boot and is reachable from Drew's iPad at `https://<host>.<tailnet>.ts.net`.

The app binds to `127.0.0.1` only. `tailscale serve` is the sole path in, so the app is never on the LAN or the internet.

- [ ] **Step 1: Switch SvelteKit to the static adapter**

```bash
cd web && npm install -D @sveltejs/adapter-static && npm uninstall @sveltejs/adapter-auto
```

`web/svelte.config.js`:

```js
import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

export default {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter({ fallback: 'index.html' })
	}
};
```

`web/src/routes/+layout.ts` (new file) turns off SSR, since there is no Node process at runtime:

```ts
export const prerender = false;
export const ssr = false;
```

- [ ] **Step 2: Build and confirm the output lands where the API expects it**

```bash
cd web && npm run build && ls build/index.html
```

Expected: `build/index.html` exists. That path matches `Settings.web_dist` (`web/build`).

- [ ] **Step 3: Verify one process serves everything**

```bash
infisical run -- uv run python -m uvicorn api.app:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```bash
curl -s localhost:8000/api/health | head -c 200; echo
curl -s -o /dev/null -w "%{http_code} html\n" localhost:8000/
curl -s -o /dev/null -w "%{http_code} image\n" localhost:8000/images/official-artwork/25.png
```

Expected: the health JSON, then `200 html` and `200 image`. If `/` returns 404 the build directory is missing or `web_dist` is wrong. If `/api/health` returns HTML, the static mount is shadowing the API and was mounted too early.

- [ ] **Step 4: Write `deploy/drews-pokemon-app.service`**

`%h` expands to the home directory, so this unit is not tied to a username. Infisical needs a machine identity for unattended runs, since an interactive login token expires. Jordan creates the identity and exports `INFISICAL_TOKEN` into `%h/.config/drews-pokemon-app.env`, which is `chmod 600` and outside the repo.

```ini
[Unit]
Description=Drew's Pokémon App
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/Developer/drew/pokemon_app
EnvironmentFile=%h/.config/drews-pokemon-app.env
ExecStart=/usr/local/bin/infisical run --projectId=${INFISICAL_PROJECT_ID} --env=prod -- \
    %h/.local/bin/uv run python -m uvicorn api.app:app --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

Confirm the two binary paths before installing, and correct the unit if they differ:

```bash
which infisical uv
```

- [ ] **Step 5: Write `deploy/install.sh`**

```bash
#!/usr/bin/env bash
# Build the frontend, install the user service, and publish it on the tailnet.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="$HOME/.config/systemd/user"
UNIT_NAME="drews-pokemon-app.service"

echo "Building the frontend..."
(cd "$REPO_ROOT/web" && npm ci && npm run build)

echo "Installing the user service..."
mkdir -p "$UNIT_DIR"
cp "$REPO_ROOT/deploy/$UNIT_NAME" "$UNIT_DIR/$UNIT_NAME"
systemctl --user daemon-reload
systemctl --user enable --now "$UNIT_NAME"

echo "Allowing the service to run without an active login..."
loginctl enable-linger "$USER"

echo "Publishing on the tailnet over HTTPS..."
sudo tailscale serve --bg 8000

echo
systemctl --user --no-pager status "$UNIT_NAME" | head -12
echo
tailscale serve status
```

```bash
chmod +x deploy/install.sh
```

- [ ] **Step 6: Set up the Infisical machine identity**

Interactive and account-level, so Jordan runs this, not the implementer. He needs a machine identity with read access to the `drew-pokemon` project, then:

```bash
mkdir -p ~/.config
cat > ~/.config/drews-pokemon-app.env <<'EOF'
INFISICAL_TOKEN=<machine identity token>
INFISICAL_PROJECT_ID=<project id from .infisical.json>
EOF
chmod 600 ~/.config/drews-pokemon-app.env
```

The project id is the `workspaceId` field in `.infisical.json`.

- [ ] **Step 7: Install and verify the service is actually running**

```bash
./deploy/install.sh
systemctl --user is-active drews-pokemon-app.service
curl -s localhost:8000/api/health | head -c 200; echo
```

Expected: `active`, then the health JSON. If it is not active, read the logs before changing anything:

```bash
journalctl --user -u drews-pokemon-app.service -n 50 --no-pager
```

- [ ] **Step 8: Verify it survives a restart**

```bash
systemctl --user restart drews-pokemon-app.service
sleep 3
curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/api/health
```

Expected: `200`.

- [ ] **Step 9: Verify the Tailscale URL and that nothing else is exposed**

```bash
tailscale serve status
tailscale status --json | python3 -c "import json,sys; print(json.load(sys.stdin)['Self']['DNSName'])"
ss -tlnp | grep 8000
```

Expected: `serve status` shows `https://<host>.<tailnet>.ts.net` proxying to `127.0.0.1:8000`, and `ss` shows the listener bound to `127.0.0.1`, not `0.0.0.0`. A `0.0.0.0` binding means the app is on the LAN and the `--host` flag in the unit is wrong.

- [ ] **Step 10: Open it on the iPad**

On Drew's iPad, connected to the tailnet, open `https://<host>.<tailnet>.ts.net`. Confirm the page loads with a valid certificate and no warning, ask one question, and confirm the artwork renders. Then Share → Add to Home Screen.

- [ ] **Step 11: Commit**

```bash
git add deploy web/svelte.config.js web/src/routes/+layout.ts web/package.json
git commit -m "feat: single-process deploy with systemd and tailscale serve"
```

---

### Task 22: End-to-end verification and README

**Files:**
- Create: `README.md`
- Modify: `docs/superpowers/plans/2026-08-15-drews-pokemon-app.md` (tick the remaining boxes)

**Interfaces:**
- Consumes: everything
- Produces: a documented, verified, running app.

- [ ] **Step 1: Start both processes**

Terminal one:

```bash
infisical run -- uv run fastapi dev api/app.py --port 8000
```

Terminal two:

```bash
cd web && npm run dev
```

- [ ] **Step 2: Verify each question type in the browser at http://localhost:5173**

Ask all four and confirm the described result. Do not tick a box you have not seen work.

| Question | Must show |
|---|---|
| "What are Gengar's abilities?" | A Pokémon card with artwork, Ghost/Poison badges, and the abilities listed |
| "Which Water type under 10 kg is the fastest?" | A `searched the whole Pokédex` chip and a result table |
| "Would Pikachu beat Onix?" | A comparison table, and text that says the pick is an opinion |
| "Build me a balanced team around Charizard" | Several cards and a reason for each pick |
| "Show me Eevee's evolutions" | An evolution line with all eight |
| "Tell me about pikchu" | A question back to Drew asking if he meant Pikachu |

- [ ] **Step 2b: Verify the cost controls actually bite**

Temporarily set the cap to a value already exceeded and confirm Drew gets a sentence, not an error:

```bash
curl -s localhost:8000/api/health | python3 -c "import json,sys; d=json.load(sys.stdin); print('spent', d['spent_today_usd'], 'of', d['daily_budget_usd'])"
```

Then, with the service stopped, run the app with a tiny cap and ask a question in the browser:

```bash
infisical run -- env POKEDEX_DAILY_BUDGET_USD=0.0000001 \
  uv run python -m uvicorn api.app:app --host 127.0.0.1 --port 8000
```

Expected: the chat replies "That's all the Pokémon questions for today, Drew. Come back tomorrow!" with no red error banner, and `usage_log` gains no new row for that attempt.

```bash
sqlite3 data/pokedex.db "SELECT day, model, input_tokens, output_tokens, round(cost_usd,6) FROM usage_log ORDER BY id DESC LIMIT 5;"
```

Expected: one row per real question asked so far, with plausible token counts. If `cost_usd` is 0 for every row, token usage is not reaching `record_usage`.

- [ ] **Step 3: Verify persistence**

Reload the page, click the conversation in the sidebar, and confirm the messages and cards come back. Then delete it and confirm it disappears from the list after a reload.

- [ ] **Step 4: Verify artwork is local**

```bash
curl -s -o /dev/null -w "%{http_code}\n" localhost:5173/images/official-artwork/94.png
```

Expected: `200`. Disconnect from the internet and reload a conversation. The artwork must still render. The chat itself will fail without internet, which is expected since OpenAI is remote.

- [ ] **Step 5: Write `README.md`**

````markdown
# Drew's Pokémon App

Ask questions about Pokémon and get answers backed by a local copy of PokeAPI.
Runs entirely on this machine apart from the OpenAI calls.

## Setup

```bash
infisical init              # once, link this folder to the drew-pokemon project
uv sync
uv run python -m ingest.sync    # ~10 minutes, downloads ~400MB of artwork
cd web && npm install
```

The OpenAI key lives in Infisical, project `drew-pokemon`. There is no `.env` file.

`ingest.sync` builds `data/pokedex.db` from PokeAPI's own CSV dump and copies
artwork into `data/images/`. Pass `--skip-images` to skip the slow part.

## Running

Development, two processes:

```bash
infisical run -- uv run fastapi dev api/app.py --port 8000   # terminal one
cd web && npm run dev                                        # terminal two
```

Open http://localhost:5173.

On the Minisforum it runs as one process under systemd, published to the tailnet:

```bash
./deploy/install.sh
systemctl --user status drews-pokemon-app.service
tailscale serve status
```

Drew opens `https://<host>.<tailnet>.ts.net` on his iPad. The app binds to
`127.0.0.1` only; Tailscale is the only way in.

## How it works

The model never answers from memory. It has five tools over the local database:
`find_pokemon`, `type_matchup`, `compare`, `evolution_chain`, and `run_sql`.
`run_sql` is guarded: one read-only SELECT, 200 rows maximum. The browser renders
Pokémon cards from the typed tool results rather than from the model's prose, so
the numbers on screen are always the numbers in the database.

Conversations are stored in the same SQLite file as the Pokédex.

## Tests

```bash
uv run pytest              # Python
cd web && npx vitest run   # frontend
```

Tests never call OpenAI. `ALLOW_MODEL_REQUESTS` is off and the agent runs against
`TestModel` and `FunctionModel`.

## Cost

Two independent limits.

Per question, `UsageLimits(request_limit=8, tool_calls_limit=12,
total_tokens_limit=20000)` stops a runaway tool loop. Per day, every turn's
tokens are priced and logged to `usage_log`, and the app refuses past
`$0.25` with a friendly message. The cap resets at local midnight.

At `gpt-5.6-luna` prices a question costs about $0.0012, so the cap is roughly
200 questions a day. The pricing table in `api/budget.py` is a hardcoded constant
and must be updated when prices change. Unknown models are priced at the most
expensive known rate so the cap never silently overspends.

```bash
curl -s localhost:8000/api/health   # spent_today_usd and daily_budget_usd
```

## Configuration

Secrets come from Infisical, injected by `infisical run --`.

| Setting | Default | Meaning |
|---|---|---|
| `OPENAI_API_KEY` | none, required | Your OpenAI key |
| `POKEDEX_OPENAI_MODEL` | `openai:gpt-5.6-luna` | Model, with the provider prefix |
| `POKEDEX_DAILY_BUDGET_USD` | `0.25` | Daily spend cap |
| `POKEDEX_REQUEST_LIMIT` | `8` | Model turns per question |
| `POKEDEX_TOOL_CALLS_LIMIT` | `12` | Tool calls per question |
| `POKEDEX_TOTAL_TOKENS_LIMIT` | `20000` | Tokens per question |
````

- [ ] **Step 6: Lint, format, and run everything once**

```bash
uv run ruff check --fix . && uv run ruff format . && uv run pytest -q
cd web && npx vitest run && npm run check
```

Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add README.md docs
git commit -m "docs: README and verified end-to-end run"
```

---

## Self-Review

Checked after writing:

- **Spec coverage.** Every spec section maps to a task. Ingest from CSVs is Tasks 2-7; images Task 6; the five tools Tasks 11-12; `run_sql` guardrails Task 10; streaming Tasks 15-16; persistence Task 14; cost control Tasks 14b, 15, 16; the cards Tasks 19-21; deployment, systemd, and Tailscale Task 21b; branding in Task 1 (`package.json`, `pyproject.toml`), Task 13 (system prompt), Task 17 (browser title), Task 21 (header, `EmptyState`); kid-friendly tone in Tasks 13, 19, 20, 21, and in both limit messages. The spec's "no battle simulator" line is enforced by the system prompt instruction to flag judgement calls, verified in Task 22 Step 2.
- **Type consistency.** `PokemonProfile`, `BaseStats`, `FindPokemonResult`, `MatchupReport`, `Comparison`, `EvolutionChain`, `SqlResult`, and `ToolEvent` are defined once in `api/models.py` (Tasks 9 and 14) and mirrored field-for-field in `web/src/lib/types.ts` (Task 17). `artwork_path`/`sprite_path` from `v_pokemon` (Task 5) become `/images/...` URLs in `api/tools.py` (Task 11) and are consumed by `PokemonCard` (Task 19). The five tool names are identical in `api/agent.py`, `ToolChip`, and `ToolResult`.
- **Cost-control consistency.** The per-run caps are defined once in `Settings` (Task 1), passed into `UsageLimits` in `api/app.py` (Task 16), threaded through `stream_turn` (Task 15), and surfaced to Drew by `LIMIT_MESSAGE`. The daily cap lives in `api/budget.py` (Task 14b), is checked before the model runs and recorded after (Task 16), shown by `/api/health`, and rendered by the `limit` branch in `chat.svelte.ts` (Task 18). Two distinct messages, both kid-friendly: `LIMIT_MESSAGE` for a loop, `BUDGET_MESSAGE` for the daily cap.
- **Two things only Jordan can do**, both called out in the steps that need them rather than assumed: `infisical init` (Task 1, Step 3) and the Infisical machine identity for the unattended service (Task 21b, Step 6).
- **Placeholders.** None. Every code step carries the actual code.
