from __future__ import annotations

import re

MAX_ROWS = 200

_FORBIDDEN = re.compile(
    r"\b(DROP|DELETE|UPDATE|INSERT|ALTER|ATTACH|DETACH|PRAGMA|CREATE|REPLACE|VACUUM|REINDEX)\b",
    re.IGNORECASE,
)
_LIMIT = re.compile(r"\bLIMIT\s+(\d+)(\s+OFFSET\s+\d+)?\s*$", re.IGNORECASE)
_STRING_LITERAL = re.compile(r"'(?:[^']|'')*'")


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
    # comment/keyword/semicolon checks below. All checks run against
    # `scrubbed`, but the SQL we return is built from `cleaned` so the
    # original query text (including string values) is preserved.
    scrubbed = _STRING_LITERAL.sub("''", cleaned)

    if "--" in scrubbed or "/*" in scrubbed:
        # A trailing line comment would silently swallow the LIMIT clause we
        # append below (e.g. "SELECT 1 --" + " LIMIT 200" comments it out),
        # so comments are rejected outright rather than stripped.
        raise UnsafeSqlError(
            "Comments are not allowed in the query. Write a single plain SELECT statement."
        )

    if ";" in scrubbed:
        raise UnsafeSqlError("Only one statement is allowed. Remove the semicolon.")

    head = scrubbed.lstrip("(").split(None, 1)[0].upper() if scrubbed.strip() else ""
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

    # Matched against `cleaned` (not `scrubbed`): the pattern is anchored to
    # the very end of the string, and a string literal containing text that
    # looks like "LIMIT 5" can never reach that end anchor unescaped because
    # its closing quote sits after it. So no separate scrub is needed here.
    match = _LIMIT.search(cleaned)
    if match is None:
        return f"{cleaned} LIMIT {MAX_ROWS}"
    if int(match.group(1)) > MAX_ROWS:
        offset_clause = match.group(2) or ""
        return f"{cleaned[: match.start()]}LIMIT {MAX_ROWS}{offset_clause}"
    return cleaned
