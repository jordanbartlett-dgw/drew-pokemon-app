# Known issues and unverified gaps

As of 2026-08-15, after the whole-branch review. Nothing here blocks Drew using
the app. Recorded so it is not rediscovered from scratch.

## Never verified

**Nothing has been seen in a browser.** There was no browser binary in the build
environment, so layout, tap targets, the iPad-portrait drawer, and streaming
scroll behaviour are unverified. Every data contract behind them was verified
over HTTP: cards render from typed tool frames that were inspected directly, all
1,025 `v_pokemon` rows resolve to artwork files that exist and are non-empty, and
six real questions answered correctly. But no one has looked at it.

Most likely first thing to hit: **the message list does not autoscroll while an
answer streams in.** The composer is `sticky bottom-4`, but nothing scrolls the
list, so a long answer grows below the fold and Drew has to scroll by hand.

**The container deploy is new (2026-11-18).** It replaced the systemd unit, which
was never installed. The image was built and run locally against the real
`data/`: health, frontend, artwork and conversations all answered. See the
README's "Deploying" section.

## Parked, with reasoning

**`Nidoran♂` / `Nidoran♀` typed with the glyph do not resolve directly.**
Introduced by the final fix wave: `find_pokemon`'s normalization strips
non-alphanumerics so that `Mr. Mime`, `Mime Jr.`, `Type: Null` and `Mr. Rime`
resolve on the first try. That same rule strips ♂/♀. Ruling: acceptable. A kid
does not type ♂; typing `nidoran` returns both as candidates, which is the
correct disambiguation for a genuinely ambiguous name, and `Nidoran-M` /
`nidoran-f` still resolve directly. One-line fix if it ever matters: try an
exact `LOWER(name)` match on the unstripped input before normalizing.

**A turn that hits a usage limit or errors still consumes one of the four
history slots**, persisting `model_messages_json = "[]"`. Harmless; slightly
shrinks effective memory after a failed turn.

**Pathological history is still theoretically possible**: 4 turns x 12 tool
calls x 4,000 chars is about 48k tokens, which could sit permanently near the
60k per-run limit. It now fails with "This chat got too long for me to
remember! Tap New question", not a silent brick, and a new conversation clears
it.

**`run_sql` with zero rows renders no table.** The `ToolChip` still shows
("searched the whole Pokédex") and the model's prose explains the result, so it
is not a dead end — but a correct zero-result query looks the same as a tool
that returned nothing.

**Alternate forms are not in `v_pokemon`.** `find_pokemon("deoxys-attack")`
returns no candidates. The view is restricted to `is_default = 1` so alternate
forms do not duplicate every row. Pre-existing and deliberate.

**No `.prettierrc` in `web/`.** Running `prettier --write` reformats away from
the codebase's tab/single-quote style. Add a config before anyone reaches for it.

## Things that will break later

**The pricing table is hardcoded and dated.** `api/budget.py`'s
`PRICING_USD_PER_MTOK` is correct as of 2026-08-15. If OpenAI raises
`gpt-5.6-luna`, the $0.25 cap silently becomes a larger cap. Unknown models
already fall back to the most expensive known rate, which fails safe.

**`run_sql` correctness is bounded by the guard, not by semantics.** The guard
proves a query is safe, not that it is right. A subtly wrong join gives Drew a
confidently wrong answer with a table next to it, and the UI's whole premise is
that on-screen numbers are database numbers. Six verified questions is a small
sample against 1,025 Pokémon.
