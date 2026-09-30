"""Information version repository on ``information_versions`` (§18.1, §27).

Revision ``0007`` created the table for the §18.1 version chains; until now the
``create_version`` / ``archive_record`` tools (§21) kept their chain in a
process-local :class:`~app.tools.governance_tools.versioning.VersionStore`, so a
restart erased the history of every governed resource.

The chain lives here, in one table, and an **archive mark is a version of the
resource that says so** (``content = {"action": "archive", ...}``,
``superseded = true``): one table, one read path, no second source of truth.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    func,
    select,
    update,
)

from app.domain.value_objects.ulid import ULID
from app.storage.repositories.table_repository import (
    JSON_TYPE,
    TableRepository,
    as_datetime,
    as_dict,
    as_iso,
    insert_rows,
    insert_statement,
)

__all__ = ["InformationVersionRepository", "information_versions_table"]

versions_metadata = MetaData()

information_versions_table = Table(
    "information_versions",
    versions_metadata,
    Column("information_version_id", String(64), primary_key=True),
    Column("information_id", String(64), nullable=False),
    Column("version", Integer, nullable=False),
    Column("content", JSON_TYPE, nullable=True),
    Column("superseded", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

#: ``content.action`` of the row that marks a resource archived.
ARCHIVE_ACTION = "archive"


def to_version_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``information_versions`` row onto its §18.1 payload."""
    data = dict(row)
    return {
        "version_id": data.get("information_version_id"),
        "resource_id": data.get("information_id"),
        "version": data.get("version"),
        "superseded": bool(data.get("superseded")),
        "created_at": as_iso(data.get("created_at")),
        "content": as_dict(data.get("content")),
    }


class InformationVersionRepository(TableRepository):
    """Persistence of the §18.1 version chains."""

    _metadata = versions_metadata
    _table = information_versions_table

    @classmethod
    async def append(
        cls, engine: Any, information_id: str, content: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Append one version to *information_id* and return it.

        The version number is computed by the database in the same statement
        (``MAX(version) + 1``), so two appends cannot silently write the same
        number for one resource.
        """
        await cls.ensure_table(engine)
        # One identity per version: when the payload already carries a
        # ``version_id`` (the durable store builds it), the row uses it, so a
        # parent link and the chain entry name the same version.
        version_id = str(content.get("version_id") or ULID.new("VER_"))
        next_version = (
            select(func.coalesce(func.max(information_versions_table.c.version), 0) + 1)
            .where(information_versions_table.c.information_id == information_id)
            .scalar_subquery()
        )
        statement = insert_statement(information_versions_table, engine).values(
            information_version_id=version_id,
            information_id=information_id,
            version=next_version,
            content=dict(content),
            superseded=False,
            created_at=datetime.now(UTC),
        )
        async with engine.begin() as conn:
            await conn.execute(statement)
        stored = await cls.get(engine, version_id)
        return stored if stored is not None else {"version_id": version_id}

    @classmethod
    async def get(cls, engine: Any, version_id: str) -> dict[str, Any] | None:
        """Return one stored version by its identifier, or ``None``."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(information_versions_table).where(
                    information_versions_table.c.information_version_id == version_id
                )
            )
            row = result.mappings().first()
        return to_version_response(row) if row else None

    @classmethod
    async def list_for(cls, engine: Any, information_id: str) -> list[dict[str, Any]]:
        """Return the whole chain of *information_id*, oldest version first."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(information_versions_table)
                .where(information_versions_table.c.information_id == information_id)
                .order_by(information_versions_table.c.version)
            )
            rows = result.mappings().all()
        return [to_version_response(row) for row in rows]

    @classmethod
    async def latest(cls, engine: Any, information_id: str) -> dict[str, Any] | None:
        """Return the most recent version of *information_id*, or ``None``."""
        chain = await cls.list_for(engine, information_id)
        return chain[-1] if chain else None

    @classmethod
    async def mark_superseded(
        cls, engine: Any, information_id: str, version: int
    ) -> None:
        """Flag one version of *information_id* as superseded."""
        await cls.ensure_table(engine)
        async with engine.begin() as conn:
            await conn.execute(
                update(information_versions_table)
                .where(
                    information_versions_table.c.information_id == information_id,
                    information_versions_table.c.version == version,
                )
                .values(superseded=True)
            )

    @classmethod
    async def archive_mark(
        cls, engine: Any, information_id: str
    ) -> dict[str, Any] | None:
        """Return the archive version of *information_id*, or ``None``."""
        for version in reversed(await cls.list_for(engine, information_id)):
            if version["content"].get("action") == ARCHIVE_ACTION:
                return version
        return None

    @classmethod
    async def append_many_in(
        cls, session: Any, information_id: str, contents: Any
    ) -> int:
        """Append pre-numbered versions inside an existing unit of work."""
        rows = []
        for version, content in enumerate(contents, start=1):
            item = dict(content)
            rows.append(
                {
                    "information_version_id": ULID.new("VER_"),
                    "information_id": information_id,
                    "version": version,
                    "content": item,
                    "superseded": False,
                    "created_at": as_datetime(item.get("timestamp"), datetime.now(UTC)),
                }
            )
        return await insert_rows(session, information_versions_table, rows)
