"""Checkpoint repository on the migrated ``execution_checkpoints`` table (§41.1).

Revision ``0005`` created the table and nothing wrote to it: the §41.1 resume
projection lived in the process (``RequestLifecycle``), so an interrupted run
left **no** durable trace — a restart could not even tell that a request had been
running. This repository is what makes the checkpoint survive, and revision
``0017`` gives it the committed steps' results so a resume does not have to
re-acquire what the interrupted run already held.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    Table,
    Text,
    delete,
    select,
)

from app.core.time import utc_now
from app.storage.repositories.table_repository import (
    JSON_TYPE,
    TableRepository,
    as_iso,
    insert_statement,
)

__all__ = ["CheckpointRepository", "execution_checkpoints_table"]

checkpoint_metadata = MetaData()

execution_checkpoints_table = Table(
    "execution_checkpoints",
    checkpoint_metadata,
    Column("checkpoint_id", Text, primary_key=True),
    Column("request_id", Text, nullable=False),
    Column("resumable", Boolean, nullable=False),
    Column("last_committed_step", Text, nullable=True),
    Column("last_committed_at", DateTime(timezone=True), nullable=True),
    Column("resume_token", Text, nullable=True),
    # Revision 0017 — what the committed steps produced, and how far they went.
    Column("step_index", Integer, nullable=True),
    Column("payload", JSON_TYPE, nullable=True),
)


def to_json_safe(value: Any) -> Any:
    """Return *value* as JSON-storable data, recursively.

    Step results carry instants (``committed_at``, freshness stamps) and, on
    some paths, small objects. ``as_json_value`` handles pydantic models at the
    top level; a checkpoint payload is nested several levels deep, so instants
    become ISO strings here and nothing non-JSON reaches the JSONB column.
    Nothing is silently dropped: an unknown object becomes its ``str``, which
    keeps the ``repr`` of what the run really produced.
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_json_safe(item) for item in value]
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return to_json_safe(dump(mode="json"))
        except TypeError:  # pragma: no cover - pydantic < 2
            return to_json_safe(dump())
    return str(value)


def to_checkpoint_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``execution_checkpoints`` row onto the §41.1 projection."""
    data = dict(row)
    return {
        "checkpoint_id": data.get("checkpoint_id"),
        "request_id": data.get("request_id"),
        "resumable": bool(data.get("resumable")),
        "last_committed_step": data.get("last_committed_step"),
        "last_committed_at": as_iso(data.get("last_committed_at")),
        "step_index": data.get("step_index"),
        "payload": data.get("payload"),
        "has_payload": bool(data.get("payload")),
    }


class CheckpointRepository(TableRepository):
    """Persistence of the §41.1 execution checkpoints (one per request)."""

    _metadata = checkpoint_metadata
    _table = execution_checkpoints_table

    @staticmethod
    def checkpoint_id(request_id: str) -> str:
        """Return the identifier of the checkpoint of *request_id*.

        A checkpoint is a singleton per request, so the identifier is derived
        from the request: a resume finds the row without a lookup index.
        """
        return f"CP_{request_id}"

    @classmethod
    async def save(
        cls,
        engine: Any,
        request_id: str,
        *,
        last_committed_step: str | None,
        step_index: int,
        payload: Sequence[Mapping[str, Any]] | None = None,
        resumable: bool = True,
        resume_token: str | None = None,
    ) -> dict[str, Any]:
        """Insert or update the checkpoint of *request_id*.

        The payload is the **cumulative** committed prefix: each save replaces
        the previous one, so the row always describes a run that can be resumed
        from its own content.
        """
        await cls.ensure_table(engine)
        now = utc_now()
        row = {
            "checkpoint_id": cls.checkpoint_id(request_id),
            "request_id": request_id,
            "resumable": resumable,
            "last_committed_step": last_committed_step,
            "last_committed_at": now,
            "resume_token": resume_token,
            "step_index": int(step_index),
            "payload": [to_json_safe(dict(item)) for item in (payload or [])],
        }
        statement = insert_statement(execution_checkpoints_table, engine).values(**row)
        statement = statement.on_conflict_do_update(
            index_elements=["checkpoint_id"],
            set_={
                "resumable": row["resumable"],
                "last_committed_step": row["last_committed_step"],
                "last_committed_at": row["last_committed_at"],
                "resume_token": row["resume_token"],
                "step_index": row["step_index"],
                "payload": row["payload"],
            },
        )
        async with engine.begin() as conn:
            await conn.execute(statement)
        return to_checkpoint_response(row)

    @classmethod
    async def get(cls, engine: Any, request_id: str) -> dict[str, Any] | None:
        """Return the checkpoint of *request_id*, or ``None``."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(execution_checkpoints_table).where(
                    execution_checkpoints_table.c.request_id == request_id
                )
            )
            row = result.mappings().first()
        return to_checkpoint_response(row) if row else None

    @classmethod
    async def clear(cls, engine: Any, request_id: str) -> bool:
        """Remove the checkpoint of *request_id* (a completed run has none)."""
        await cls.ensure_table(engine)
        async with engine.begin() as conn:
            result = await conn.execute(
                delete(execution_checkpoints_table).where(
                    execution_checkpoints_table.c.request_id == request_id
                )
            )
        return bool(result.rowcount)
