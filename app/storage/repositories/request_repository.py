"""Request repository on the migrated ``requests`` table (§7, §27, §41.1).

The API used to keep every Information Request in a module-level dict
(``app/api/v1/requests/router.py:23``): a restart, a rebuild or a second worker
made the history vanish — and with it the ability to resume a run (§41.1).

What the table carries is exactly what survives a restart: identity, objective,
requester, constraints, lifecycle status and the §41.1 checkpoint. The §7 fields
the table does not carry (question, context, required_information,
required_output, permissions, budget) are **not** silently re-invented on read;
the router documents them as volatile until a migration stores them.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    select,
    update,
)

from app.core.time import utc_now
from app.storage.repositories.table_repository import (
    JSON_TYPE,
    TableRepository,
    as_datetime,
    as_dict,
    as_iso,
    insert_rows,
)

__all__ = ["RequestRepository", "requests_table"]

requests_metadata = MetaData()

requests_table = Table(
    "requests",
    requests_metadata,
    Column("request_id", String(64), primary_key=True),
    Column("request_type", String(40), nullable=False),
    Column("objective", Text, nullable=False),
    Column("requester", JSON_TYPE, nullable=True),
    Column("constraints", JSON_TYPE, nullable=True),
    Column("status", String(40), nullable=False),
    Column("ttl_seconds", Integer, nullable=False),
    Column("resumable", Boolean, nullable=False),
    Column("last_committed_step", String(64), nullable=True),
    Column("last_committed_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=True),
    # Revision 0016 — §7: the whole request body (question, context,
    # required_information, required_output, permissions, budget…), so a request
    # read back after a restart is the one that was asked, not a subset.
    Column("payload", JSON_TYPE, nullable=True),
)

#: Default lifetime of a request in seconds (the 0007 server default).
DEFAULT_TTL_SECONDS = 900


def as_json_value(value: Any) -> Any:
    """Return *value* as JSON-serializable data (pydantic models included).

    The API hands over ``RequestConstraints`` / ``RequiredOutput`` instances
    (§32), not dicts: storing them as-is would fail in the JSONB column. The
    conversion lives here so every caller of the repository gets the same
    behaviour.
    """
    if value is None or isinstance(value, (dict, list, str, int, float, bool)):
        return value
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json")
        except TypeError:  # pragma: no cover - pydantic < 2
            return dump()
    return value


def to_request_row(request: Mapping[str, Any]) -> dict[str, Any]:
    """Map a §7 request payload onto its ``requests`` row."""
    item = dict(request)
    now = utc_now()
    created_at = as_datetime(item.get("created_at"), now) or now
    return {
        "request_id": item.get("request_id"),
        "request_type": item.get("request_type") or "research",
        "objective": item.get("objective") or "",
        "requester": as_json_value(item.get("requester")),
        "constraints": as_json_value(item.get("constraints")),
        "status": item.get("status") or "received",
        "ttl_seconds": int(item.get("ttl_seconds") or DEFAULT_TTL_SECONDS),
        "resumable": bool(item.get("resumable", False)),
        "last_committed_step": item.get("last_committed_step"),
        "last_committed_at": as_datetime(item.get("last_committed_at")),
        "created_at": created_at,
        "updated_at": as_datetime(item.get("updated_at"), now),
        # §7/0016 — stored as-is when the caller brings it: the repository never
        # re-shapes the request, and ``None`` means "this row predates 0016".
        "payload": as_json_value(item.get("payload")),
    }


def to_request_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``requests`` row onto the durable subset of every §7 field."""
    data = dict(row)
    return {
        "request_id": data.get("request_id"),
        "request_type": data.get("request_type"),
        "objective": data.get("objective"),
        "requester": as_dict(data.get("requester")),
        "constraints": as_dict(data.get("constraints")),
        "status": data.get("status"),
        "ttl_seconds": data.get("ttl_seconds"),
        "resumable": bool(data.get("resumable")),
        "last_committed_step": data.get("last_committed_step"),
        "last_committed_at": as_iso(data.get("last_committed_at")),
        "created_at": as_iso(data.get("created_at")),
        "updated_at": as_iso(data.get("updated_at")),
        # ``None`` for a row written before revision 0016: the caller falls back
        # to the durable columns instead of inventing the missing §7 fields.
        "payload": as_dict(data.get("payload")) or None,
    }


class RequestRepository(TableRepository):
    """Persistence of the §7 Information Requests and their §41.1 checkpoint."""

    _metadata = requests_metadata
    _table = requests_table

    @classmethod
    async def create(cls, engine: Any, request: Mapping[str, Any]) -> dict[str, Any]:
        """Insert a request and return its durable representation."""
        await cls.ensure_table(engine)
        row = to_request_row(request)
        await insert_rows(engine, requests_table, [row], conflict_columns=("request_id",))
        stored = await cls.get(engine, str(row["request_id"]))
        return stored if stored is not None else to_request_response(row)

    @classmethod
    async def get(cls, engine: Any, request_id: str) -> dict[str, Any] | None:
        """Return one request by its identifier, or ``None``."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(requests_table).where(requests_table.c.request_id == request_id)
            )
            row = result.mappings().first()
        return to_request_response(row) if row else None

    @classmethod
    async def list_recent(cls, engine: Any, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent requests, newest first."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(requests_table)
                .order_by(requests_table.c.created_at.desc())
                .limit(limit)
            )
            rows = result.mappings().all()
        return [to_request_response(row) for row in rows]

    @classmethod
    async def update_status(
        cls, engine: Any, request_id: str, status: str, *, step: str | None = None
    ) -> None:
        """Set the lifecycle status and, when given, the §41.1 checkpoint."""
        now = utc_now()
        values: dict[str, Any] = {"status": status, "updated_at": now}
        if step is not None:
            values["last_committed_step"] = step
            values["last_committed_at"] = now
        await cls.ensure_table(engine)
        async with engine.begin() as conn:
            await conn.execute(
                update(requests_table)
                .where(requests_table.c.request_id == request_id)
                .values(**values)
            )

    @classmethod
    async def list_ids_for_actor(cls, engine: Any, actor_id: str) -> list[str]:
        """Return the ids of the requests that name *actor_id* as requester (§41.9).

        La relation est celle du modèle, pas une convention inventée :
        ``requests.requester`` porte le demandeur tel que le client l'envoie
        (``{"type": "agent", "id": "..."}``), et ``requester.id`` est ce qui
        nomme un acteur. Les demandes reviennent, la plus récente d'abord.
        """
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(requests_table.c.request_id)
                .where(requests_table.c.requester["id"].as_string() == actor_id)
                .order_by(requests_table.c.created_at.desc())
            )
        return [str(row[0]) for row in result.fetchall()]
