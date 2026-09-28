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

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import MetaData, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.types import JSON

#: JSON column type: JSONB on PostgreSQL, JSON elsewhere.
JSON_TYPE = JSON().with_variant(postgresql.JSONB(), "postgresql")

__all__ = ["JSON_TYPE", "TableRepository", "as_dict", "as_iso"]


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
            moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return default
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
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
