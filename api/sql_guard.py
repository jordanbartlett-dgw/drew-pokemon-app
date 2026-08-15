from __future__ import annotations

import re

MAX_ROWS = 200

_FORBIDDEN = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|ATTACH|DETACH|PRAGMA|CREATE|REPLACE|VACUUM|REINDEX)\b",
    re.IGNORECASE,
)
_LIMIT_KEYWORD = re.compile(r"\bLIMIT\b", re.IGNORECASE)
# The only two LIMIT shapes we support: a plain non-negative integer, and
# that integer plus an OFFSET. SQLite's actual grammar also allows negative
# integers, floats, hex literals, arithmetic expressions, and a `LIMIT a,b`
# offset-then-count form -- all syntactically valid on their own, but every
# one of them would silently produce a double-LIMIT syntax error once we
# append or substitute our own `LIMIT {MAX_ROWS}`, so anything outside these
# two shapes is rejected rather than guessed at.
_LIMIT_CLAUSE = re.compile(r"^\s+(\d+)(\s+OFFSET\s+\d+)?\s*$", re.IGNORECASE)
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")


def _blank_strings(text: str) -> str:
    """Replace string literal contents with '#' filler, keeping the length the same.

    Preserving length keeps character offsets identical between the scrubbed
    text and the original, so positions found by searching the scrubbed text
    can be used to slice the original directly.
    """
    return _STRING_LITERAL.sub(lambda m: "'" + "#" * (len(m.group(0)) - 2) + "'", text)


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

    # Blank out string literal contents first so keywords or markers inside a
    # legitimate value (e.g. WHERE name = 'Porygon-Z') never trigger the
    # comment/keyword/semicolon/LIMIT checks below. All checks run against
    # `scrubbed`, but the SQL we return is built from `cleaned` so the
    # original query text (including string values) is preserved. The blank
    # filler keeps the same length as the original literal, so any position
    # found in `scrubbed` is also a valid position in `cleaned`.
    scrubbed = _blank_strings(cleaned)

    if "--" in scrubbed or "/*" in scrubbed:
        # A trailing line comment would silently swallow the LIMIT clause we
        # append below (e.g. "SELECT 1 --" + " LIMIT 200" comments it out),
        # so comments are rejected outright rather than stripped.
        raise UnsafeSqlError(
            "Comments are not allowed in the query. Write a single plain SELECT statement."
        )

    if ";" in scrubbed:
        raise UnsafeSqlError("Only one statement is allowed. Remove the semicolon.")

    # A leading '(' is rejected outright rather than stripped. Wrapping the
    # whole statement in parentheses (or unioning two parenthesized SELECTs)
    # is syntactically valid SQLite on its own, but the LIMIT clause we
    # append lands after the closing paren, e.g. "(SELECT ...) LIMIT 200",
    # which SQLite rejects as a syntax error near "(" -- the same
    # accept-but-unexecutable outcome already fixed for LIMIT arguments.
    # There's no legitimate need for a wrapped top-level statement here: the
    # model can always write the unwrapped form instead. Parens elsewhere
    # (a FROM subquery, a scalar subquery, WHERE ... IN (...), a CTE body)
    # are untouched since only a paren at the very start is checked.
    stripped = scrubbed.strip()
    if stripped.startswith("("):
        raise UnsafeSqlError(
            "Do not wrap the query in parentheses. Start the statement with SELECT or "
            "WITH directly, e.g. 'SELECT ...' not '(SELECT ...)'."
        )

    head = stripped.split(None, 1)[0].upper() if stripped else ""
    if head not in {"SELECT", "WITH"}:
        raise UnsafeSqlError(
            f"Queries must start with SELECT or WITH, got {head or 'nothing'}. "
            "This database is read-only."
        )

    if _FORBIDDEN.search(scrubbed):
        raise UnsafeSqlError(
            "Only read-only SELECT queries are allowed. Nothing that changes or inspects "
            "the database structure (no DROP, DELETE, UPDATE, INSERT, ALTER, ATTACH, "
            "DETACH, PRAGMA, CREATE, REPLACE, VACUUM, or REINDEX)."
        )

    # Find the outermost, trailing `LIMIT` keyword outside of any string
    # literal. A query can legitimately contain an earlier LIMIT scoped to a
    # subquery (e.g. `SELECT * FROM (SELECT * FROM v_pokemon LIMIT 1) LIMIT
    # 5`, or `SELECT * FROM (SELECT * FROM v_pokemon LIMIT 5) AS t` with no
    # outer LIMIT at all) -- only the clause that actually caps the final
    # result set matters for enforcement; a LIMIT still followed by an
    # unmatched `)` is scoped to a subquery that closes later, so it's
    # skipped. Walk right-to-left so the first candidate found is the
    # rightmost one that is not nested this way.
    candidate = None
    for keyword in reversed(list(_LIMIT_KEYWORD.finditer(scrubbed))):
        suffix = scrubbed[keyword.end() :]
        if suffix.count(")") > suffix.count("("):
            continue  # scoped to a subquery that closes later; not the trailing clause
        candidate = keyword
        break

    if candidate is None:
        return f"{cleaned} LIMIT {MAX_ROWS}"

    clause = scrubbed[candidate.end() :]
    clause_match = _LIMIT_CLAUSE.match(clause)
    if clause_match is None:
        raise UnsafeSqlError(
            "The LIMIT clause must be a plain whole number, like 'LIMIT 50', optionally "
            "with OFFSET, like 'LIMIT 50 OFFSET 10'. Forms like 'LIMIT a,b', 'LIMIT -1', "
            "and expressions are not supported."
        )

    limit_value = int(clause_match.group(1))
    if limit_value > MAX_ROWS:
        offset_clause = clause_match.group(2) or ""
        return f"{cleaned[: candidate.start()]}LIMIT {MAX_ROWS}{offset_clause}"
    return cleaned
