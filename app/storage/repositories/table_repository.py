"""Shared helpers for the §27 table repositories.

One responsibility: keep the SQL plumbing of the repositories in a single
place so each repository only describes *its* table and row mapping. SQL and
SQLAlchemy stay in ``app.storage`` (CODING_RULES §2).

Schema ownership: on PostgreSQL the schema belongs to Alembic (§41.14), so
:meth:`TableRepository.ensure_table` never calls ``create_all`` there. On other
dialects (SQLite in dev/tests) the tables are created from the same Core
metadata, which keeps the repositories usable without a PostgreSQL server.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import MetaData, Table, func, insert
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.types import JSON

#: JSON column type: JSONB on PostgreSQL, JSON elsewhere.
JSON_TYPE = JSON().with_variant(postgresql.JSONB(), "postgresql")

__all__ = [
    "JSON_TYPE",
    "TableRepository",
    "as_datetime",
    "as_dict",
    "as_iso",
    "dialect_of",
    "insert_rows",
    "insert_statement",
]


def dialect_of(executor: Any) -> str:
    """Return the dialect name behind an engine, a connection or a session.

    The persistence helpers accept all three: a repository owns its transaction
    (an engine), while a pipeline writes several tables in *one* unit of work (a
    live session). The dialect is what decides whether ``ON CONFLICT`` can be
    expressed at all.
    """
    bind = getattr(executor, "bind", None) or getattr(executor, "engine", None) or executor
    return str(getattr(getattr(bind, "dialect", None), "name", ""))


def insert_statement(table: Table, executor: Any) -> Any:
    """Return the ``INSERT`` construct of *table* for *executor*'s dialect.

    PostgreSQL gets ``postgresql.insert`` so ``on_conflict_*`` can be attached;
    every other dialect (SQLite in dev/tests) gets the plain statement — the
    migration-managed schema is PostgreSQL (§41.14), the rest is a convenience.
    """
    if dialect_of(executor) == "postgresql":
        from sqlalchemy.dialects.postgresql import insert as pg_insert

        return pg_insert(table)
    return insert(table)


async def insert_rows(
    executor: Any,
    table: Table,
    rows: Sequence[Mapping[str, Any]],
    *,
    conflict_columns: Sequence[str] | None = None,
    update_columns: Sequence[str] = (),
    coalesce_columns: Sequence[str] = (),
) -> int:
    """Insert *rows* through *executor* and return how many were sent.

    Args:
        executor: A live :class:`AsyncSession` / connection (the caller owns the
            transaction) or an :class:`AsyncEngine` (this function opens one).
        table: The Core table the rows belong to.
        rows: Row mappings; an empty sequence is a no-op.
        conflict_columns: Columns of the conflict target. Without them, no
            ``ON CONFLICT`` clause is added.
        update_columns: On conflict, overwrite these columns with the new value.
        coalesce_columns: On conflict, overwrite these columns only when the new
            value is not ``NULL`` (the behaviour ``sources`` needs for
            ``reliability_score``: a re-acquisition that measured nothing must
            not erase what an earlier run measured).
    """
    if not rows:
        return 0
    payload = [dict(row) for row in rows]
    statement = insert_statement(table, executor)
    if conflict_columns and dialect_of(executor) == "postgresql":
        if update_columns or coalesce_columns:
            assignment: dict[str, Any] = {
                name: statement.excluded[name] for name in update_columns
            }
            assignment.update(
                {
                    name: func.coalesce(statement.excluded[name], table.c[name])
                    for name in coalesce_columns
                }
            )
            statement = statement.on_conflict_do_update(
                index_elements=list(conflict_columns), set_=assignment
            )
        else:
            statement = statement.on_conflict_do_nothing(
                index_elements=list(conflict_columns)
            )
    if isinstance(executor, AsyncEngine):
        async with executor.begin() as connection:
            await connection.execute(statement, payload)
        return len(payload)
    await executor.execute(statement, payload)
    return len(payload)


def as_dict(value: Any) -> dict[str, Any]:
    """Return *value* as a dict, tolerating JSON stored as a plain string."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        import json

        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def as_iso(value: Any) -> str | None:
    """Return *value* as an ISO 8601 string (SQLite returns raw strings)."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def as_datetime(value: Any, default: datetime | None = None) -> datetime | None:
    """Return *value* as a timezone-aware ``datetime`` (ISO 8601 accepted)."""
    if value is None:
        return default
    if isinstance(value, datetime):
        moment = value
    else:
        try:
            # ``fromisoformat`` accepts the ``Z`` suffix since Python 3.11.
            moment = datetime.fromisoformat(str(value))
        except ValueError:
            return default
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment


class TableRepository:
    """Base class binding a repository to one Core table."""

    _metadata: MetaData
    _table: Table

    @classmethod
    async def ensure_table(cls, engine: Any) -> None:
        """Create the table when the dialect is not PostgreSQL.

        PostgreSQL schemas come from Alembic migrations only (§41.14): calling
        ``create_all`` there could hide a migration drift or create a table the
        migration did not plan.
        """
        if getattr(engine.dialect, "name", "") == "postgresql":
            return
        async with engine.begin() as conn:
            await conn.run_sync(cls._metadata.create_all)
