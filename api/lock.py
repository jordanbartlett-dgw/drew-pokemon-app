from __future__ import annotations

import threading

# Shared by api/store.py and api/budget.py. api/main.py opens ONE sqlite3.Connection
# on settings.store_path and hands it to both modules (conversations and the daily
# usage log live in the same file). Two independent module-level locks would let a
# save_turn() and a record_usage() run concurrently on that one connection -- each
# module's own statements look atomic in isolation, but sqlite3 does not serialize
# access across separate Python-level locks, so the two could interleave mid-INSERT.
# api/db.py's lock is intentionally NOT this one: it guards a different, separate
# connection (the read-only Pokédex) and has nothing to share a lock with.
store_lock = threading.Lock()
