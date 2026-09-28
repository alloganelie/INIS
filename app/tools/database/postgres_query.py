"""``postgres_query`` internal tool per §21.

INIS must not execute arbitrary code (§1.2) nor mutate a source it only reads,
so the tool accepts **read-only** SQL exclusively:

* the statement must start with ``SELECT`` or ``WITH`` (a data-modifying CTE such
  as ``WITH x AS (DELETE …)`` is rejected too);
* forbidden keywords (``insert``, ``update``, ``delete``, ``drop``, ``alter``,
  ``create``, ``truncate``, ``grant``, ``copy``, ``vacuum``…) are refused;
* statement stacking (``;`` followed by more SQL) is refused;
* every value travels as a bound parameter, never interpolated;
* a ``LIMIT`` guard is appended when the statement has none.

Every rejection raises :class:`~app.core.errors.ValidationError` before a
connection is opened.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import InfrastructureError, ValidationError
from app.storage.database.engine import create_engine

__all__ = ["postgres_query", "assert_read_only"]

#: Statement prefixes PostgreSQL allows for a read-only query.
_ALLOWED_PREFIXES = ("select", "with")

#: Keywords that make a statement (or a CTE) a write.
_FORBIDDEN_KEYWORDS = frozenset(
    {
        "insert",
        "update",
        "delete",
        "drop",
        "alter",
        "create",
        "truncate",
        "grant",
        "revoke",
        "copy",
        "vacuum",
        "analyze",
        "reindex",
        "refresh",
        "call",
        "do",
        "set",
        "commit",
        "rollback",
    }
)

_COMMENT_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_WORD_RE = re.compile(r"[A-Za-z_]+")
_LIMIT_RE = re.compile(r"\blimit\b", re.IGNORECASE)

#: Row cap applied when the caller's statement carries no ``LIMIT``.
DEFAULT_MAX_ROWS = 1000


def assert_read_only(sql: str) -> str:
    """Validate that *sql* is a single read-only statement and return it trimmed.

    Args:
        sql: Candidate SQL statement.

    Returns:
        The statement with its trailing semicolon removed.

    Raises:
        ValidationError: If the statement is empty, not a ``SELECT``/``WITH``
            query, contains a write keyword, or stacks several statements.
    """
    if not isinstance(sql, str) or not sql.strip():
        raise ValidationError("sql must be a non-empty string")

    stripped = _COMMENT_RE.sub(" ", sql).strip()
    body = stripped.rstrip(";").strip()
    if not body:
        raise ValidationError("sql must contain a statement")

    if ";" in body:
        raise ValidationError("sql must contain exactly one statement (statement stacking refused)")

    lowered = body.lower()
    first_word = _WORD_RE.match(lowered)
    if first_word is None or first_word.group(0) not in _ALLOWED_PREFIXES:
        raise ValidationError(
            "sql must start with SELECT or WITH: postgres_query is read-only (§1.2)"
        )

    keywords = {word.lower() for word in _WORD_RE.findall(lowered)}
    forbidden = keywords & _FORBIDDEN_KEYWORDS
    if forbidden:
        raise ValidationError(
            f"sql contains forbidden keyword(s): {', '.join(sorted(forbidden))}"
        )

    return body


async def postgres_query(
    sql: str,
    params: Mapping[str, Any] | None = None,
    *,
    connection_string: str | None = None,
    engine: AsyncEngine | None = None,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> list[dict]:
    """Run a read-only SQL query and return its rows as mappings (§21).

    Args:
        sql: ``SELECT``/``WITH`` statement using ``:named`` bind parameters.
        params: Bind parameters; never interpolated into the statement.
        connection_string: PostgreSQL connection string, used when *engine* is
            omitted.
        engine: Optional pre-built async engine (shared pool, used by tests).
        max_rows: Row cap appended when the statement has no ``LIMIT``.

    Returns:
        One mapping per returned row.

    Raises:
        ValidationError: If the statement is not read-only, no engine can be
            built, or *max_rows* is not positive.
        InfrastructureError: If the query fails.
    """
    statement = assert_read_only(sql)
    if max_rows < 1:
        raise ValidationError("max_rows must be >= 1")

    if engine is None:
        if not connection_string:
            raise InfrastructureError(
                "no PostgreSQL engine available: pass an engine or a connection string"
            )
        engine = create_engine(connection_string)

    if not _LIMIT_RE.search(statement):
        statement = f"{statement} LIMIT {max_rows}"

    try:
        async with engine.connect() as connection:
            result = await connection.execute(text(statement), dict(params or {}))
            rows = [dict(row) for row in result.mappings().all()]
    except Exception as exc:
        raise InfrastructureError(f"postgres_query failed: {exc}") from exc
    return rows
