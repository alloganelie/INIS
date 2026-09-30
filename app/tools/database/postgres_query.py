"""``postgres_query`` internal tool per §21.

INIS must not execute arbitrary code (§1.2) nor mutate a source it only reads,
so the tool accepts **read-only** SQL exclusively:

* the statement must start with ``SELECT`` or ``WITH`` (a data-modifying CTE such
  as ``WITH x AS (DELETE …)`` is rejected too);
* forbidden keywords (``insert``, ``update``, ``delete``, ``drop``, ``alter``,
  ``create``, ``truncate``, ``grant``, ``copy``, ``vacuum``…) are refused;
* statement stacking (``;`` followed by more SQL) is refused;
* every value travels as a bound parameter, never interpolated;
* a ``LIMIT`` guard is appended when the statement has none;
* the query runs inside a **READ ONLY** transaction with a ``statement_timeout``
  (§41.13): even if the textual guard were bypassed, PostgreSQL itself refuses a
  write, and a runaway query is cut off instead of holding a connection;
* the connection comes from the §41.4 **vault** (``credential_ref``), never from
  a DSN written in the request (``app.tools.database.credentials``).

Every rejection raises :class:`~app.core.errors.ValidationError` before a
connection is opened.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from app.core.errors import InfrastructureError, ValidationError
from app.tools.database.credentials import dsn_from_vault
from app.tools.engine_access import resolve_engine

if TYPE_CHECKING:  # pragma: no cover - typing only
    from sqlalchemy.ext.asyncio import AsyncEngine

    from app.security.vault.credential_vault import CredentialVault

__all__ = [
    "DEFAULT_MAX_ROWS",
    "DEFAULT_STATEMENT_TIMEOUT_MS",
    "MAX_STATEMENT_TIMEOUT_MS",
    "STATEMENT_TIMEOUT_ENV",
    "assert_read_only",
    "effective_statement_timeout_ms",
    "postgres_query",
]

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

#: §41.13 — execution time of one query, mirrored by ``[limits]`` in spirit:
#: the deployment's operational ceiling is the environment variable, and the
#: default below is what every ``configs/*.toml`` assumes.
DEFAULT_STATEMENT_TIMEOUT_MS = 5_000

#: Hard ceiling: a request may ask for a shorter timeout, never for a longer
#: one than the platform grants.
MAX_STATEMENT_TIMEOUT_MS = 120_000

#: Environment variable overriding :data:`DEFAULT_STATEMENT_TIMEOUT_MS`.
STATEMENT_TIMEOUT_ENV = "INIS_POSTGRES_STATEMENT_TIMEOUT_MS"


def _positive_int(value: Any) -> int | None:
    """Return *value* as a positive ``int``, or ``None`` when unusable."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def effective_statement_timeout_ms() -> int:
    """Return the active ``statement_timeout`` ceiling in milliseconds.

    The environment wins when it carries a usable value; an unusable one is
    ignored rather than turned into "no timeout" (§0.2: a limit that cannot be
    read must not become an unlimited query).
    """
    override = _positive_int(os.getenv(STATEMENT_TIMEOUT_ENV))
    return min(override, MAX_STATEMENT_TIMEOUT_MS) if override else DEFAULT_STATEMENT_TIMEOUT_MS


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
    credential_ref: str | None = None,
    vault: CredentialVault | None = None,
    connection_string: str | None = None,
    engine: AsyncEngine | None = None,
    max_rows: int = DEFAULT_MAX_ROWS,
    statement_timeout_ms: int | None = None,
) -> list[dict]:
    """Run a read-only SQL query and return its rows as mappings (§21).

    Args:
        sql: ``SELECT``/``WITH`` statement using ``:named`` bind parameters.
        params: Bind parameters; never interpolated into the statement.
        credential_ref: §41.4 vault entry naming the database to query. This is
            the only way a *request* may choose its database: a DSN is refused by
            :func:`~app.tools.database.credentials.assert_credential_ref`.
        vault: Vault to read; the deployment's vault when omitted.
        connection_string: PostgreSQL URL for internal callers (jobs, tests).
            Never fed from a request payload.
        engine: Pre-built async engine (shared pool); when supplied it is used
            as-is and no connection is resolved.
        max_rows: Row cap appended when the statement has no ``LIMIT``.
        statement_timeout_ms: Per-call ``statement_timeout``; the platform
            ceiling applies otherwise.

    Returns:
        One mapping per returned row.

    Raises:
        ValidationError: If the statement is not read-only, *max_rows* or
            *statement_timeout_ms* is not positive, or *credential_ref* does not
            name a vault entry.
        InfrastructureError: If no engine can be built or the query fails.
    """
    statement = assert_read_only(sql)
    if max_rows < 1:
        raise ValidationError("max_rows must be >= 1")

    timeout_ms = (
        effective_statement_timeout_ms()
        if statement_timeout_ms is None
        else _positive_int(statement_timeout_ms)
    )
    if timeout_ms is None:
        raise ValidationError("statement_timeout_ms must be >= 1")
    timeout_ms = min(timeout_ms, MAX_STATEMENT_TIMEOUT_MS)

    if engine is None and credential_ref:
        # §41.4 — the secret comes from the vault, never from the request.
        connection_string = dsn_from_vault(credential_ref, vault=vault)
    active_engine = resolve_engine(engine, connection_string, component="postgres_query")

    if not _LIMIT_RE.search(statement):
        statement = f"{statement} LIMIT {max_rows}"

    try:
        async with active_engine.begin() as connection:
            # Both settings are transaction-scoped: `SET LOCAL` cannot leak to the
            # next user of this pooled connection, and READ ONLY makes PostgreSQL
            # itself refuse a write even if the textual guard above missed one.
            # `timeout_ms` is a coerced integer, never interpolated text.
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            await connection.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
            result = await connection.execute(text(statement), dict(params or {}))
            rows = [dict(row) for row in result.mappings().all()]
    except Exception as exc:
        raise InfrastructureError(f"postgres_query failed: {exc}") from exc
    return rows
