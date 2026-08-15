# Drew's Pokémon App

Ask questions about Pokémon and get answers backed by a local copy of PokeAPI.
Runs entirely on this machine apart from the OpenAI calls.

## Setup

```bash
infisical init              # once, link this folder to the drew-pokemon project
uv sync
uv run python -m ingest.sync    # downloads ~171MB of artwork (2,680 files); takes a few minutes, longer on a slow connection
cd web && npm install
```

The OpenAI key lives in Infisical, project `drew-pokemon`. There is no `.env` file.

`ingest.sync` builds `data/pokedex.db` from PokeAPI's own CSV dump and copies
artwork into `data/images/`. Pass `--skip-images` to skip the slow part.

## Running

Development, two processes:

```bash
infisical run -- uv run uvicorn api.app:app --port 8000 --reload   # terminal one
cd web && npm run dev                                              # terminal two
```

Open http://localhost:5173. Vite proxies `/api` and `/images` to `:8000`.

Do not use `fastapi dev`; it requires `fastapi[standard]`, which is not a
dependency of this project. `uv run uvicorn ...` is the supported entry point.

On the Minisforum it runs as a single process under systemd, published to the
tailnet:

```bash
./deploy/install.sh
systemctl --user status drews-pokemon-app.service
tailscale serve status
```

`install.sh` builds the frontend into `web/build`, installs the user systemd
unit, and publishes port 8000 over Tailscale HTTPS. It needs an Infisical
machine identity configured on the Minisforum (`infisical run --` in the unit
authenticates as that identity, not as a logged-in user) and `sudo` for
`tailscale serve`. Both are things only Jordan sets up; the script preflights
that the `infisical` and `uv` binary paths in the unit still match what's on
`PATH` before touching anything.

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

At `openai:gpt-5.6-luna` prices ($0.20 / $1.20 per million input/output
tokens) a real question costs roughly $0.0004-$0.0012 depending on how many
tool calls it takes, so the cap is comfortably 200+ questions a day. The
pricing table in `api/budget.py` is a hardcoded constant and must be updated
when prices change. Unknown models are priced at the most expensive known
rate so the cap never silently overspends.

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
