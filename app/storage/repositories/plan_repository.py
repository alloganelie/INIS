"""Plan repository on the migrated ``plans`` / ``plan_steps`` tables (§8, §27).

Revision ``0007`` created both tables and, until now, the planner kept its plan
in the process: a restart lost the steps a request had executed. The repository
gives the §8 plan the same durability as the delivery it produces.

``plan_steps.inputs`` / ``plan_steps.result`` are JSONB: the step payload is
stored as it was executed, so a replayed plan can be compared with what actually
happened instead of being re-invented.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, Text, select, update

from app.core.time import utc_now
from app.domain.value_objects.ulid import ULID
from app.storage.repositories.table_repository import (
    JSON_TYPE,
    TableRepository,
    as_datetime,
    as_dict,
    as_iso,
    insert_rows,
)

__all__ = ["PlanRepository", "plan_steps_table", "plans_table"]

plans_metadata = MetaData()

plans_table = Table(
    "plans",
    plans_metadata,
    Column("plan_id", String(64), primary_key=True),
    Column("request_id", String(64), nullable=False),
    Column("status", String(40), nullable=False),
    Column("objective", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=True),
)

plan_steps_table = Table(
    "plan_steps",
    plans_metadata,
    Column("step_id", String(64), primary_key=True),
    Column("plan_id", String(64), nullable=False),
    Column("step_index", Integer, nullable=False),
    Column("action", String(200), nullable=False),
    Column("tool", String(200), nullable=True),
    Column("status", String(40), nullable=False),
    Column("inputs", JSON_TYPE, nullable=True),
    Column("result", JSON_TYPE, nullable=True),
)

#: ``plan_steps`` has no ``created_at``: ``step_index`` *is* the order, and the
#: step rows are replaced wholesale by :meth:`PlanRepository.replace_steps`.


def to_plan_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``plans`` row onto the §8 payload."""
    data = dict(row)
    return {
        "plan_id": data.get("plan_id"),
        "request_id": data.get("request_id"),
        "status": data.get("status"),
        "objective": data.get("objective"),
        "created_at": as_iso(data.get("created_at")),
    }


def to_step_response(row: Mapping[str, Any]) -> dict[str, Any]:
    """Map one ``plan_steps`` row onto the §8 payload."""
    data = dict(row)
    return {
        "step_id": data.get("step_id"),
        "plan_id": data.get("plan_id"),
        "step_index": data.get("step_index"),
        "action": data.get("action"),
        "tool": data.get("tool"),
        "status": data.get("status"),
        "inputs": as_dict(data.get("inputs")),
        "result": as_dict(data.get("result")),
    }


class PlanRepository(TableRepository):
    """Persistence of the §8 plans and their steps."""

    _metadata = plans_metadata
    _table = plans_table

    @classmethod
    async def create(cls, engine: Any, plan: Mapping[str, Any]) -> dict[str, Any]:
        """Insert a plan and return its §8 representation.

        The identifier is generated when the caller does not bring one, so a
        caller that replays a stored plan keeps its original identifier.
        """
        await cls.ensure_table(engine)
        item = dict(plan)
        plan_id = str(item.get("plan_id") or ULID.new("PLAN_"))
        row = {
            "plan_id": plan_id,
            "request_id": item.get("request_id"),
            "status": item.get("status") or "draft",
            "objective": item.get("objective"),
            "created_at": as_datetime(item.get("created_at"), utc_now()),
        }
        await insert_rows(engine, plans_table, [row])
        created = await cls.get(engine, plan_id)
        return created if created is not None else to_plan_response(row)

    @classmethod
    async def get(cls, engine: Any, plan_id: str) -> dict[str, Any] | None:
        """Return one plan by its identifier, or ``None``."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(plans_table).where(plans_table.c.plan_id == plan_id)
            )
            row = result.mappings().first()
        return to_plan_response(row) if row else None

    @classmethod
    async def list_for_request(cls, engine: Any, request_id: str) -> list[dict[str, Any]]:
        """Return the plans recorded for one request, oldest first."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(plans_table)
                .where(plans_table.c.request_id == request_id)
                .order_by(plans_table.c.created_at)
            )
            rows = result.mappings().all()
        return [to_plan_response(row) for row in rows]

    @classmethod
    async def update_status(cls, engine: Any, plan_id: str, status: str) -> None:
        """Set the status of one plan."""
        await cls.ensure_table(engine)
        async with engine.begin() as conn:
            await conn.execute(
                update(plans_table).where(plans_table.c.plan_id == plan_id).values(status=status)
            )

    @classmethod
    async def add_steps(
        cls, engine: Any, plan_id: str, steps: Sequence[Mapping[str, Any]]
    ) -> int:
        """Insert *steps* for *plan_id*; ``step_index`` defaults to the order."""
        await cls.ensure_table(engine)
        rows = []
        for position, step in enumerate(steps, start=1):
            item = dict(step)
            rows.append(
                {
                    "step_id": str(item.get("step_id") or ULID.new("STEP_")),
                    "plan_id": plan_id,
                    "step_index": int(item.get("step_index") or position),
                    "action": item.get("action") or "collect_information",
                    "tool": item.get("tool"),
                    "status": item.get("status") or "pending",
                    "inputs": item.get("inputs"),
                    "result": item.get("result"),
                }
            )
        return await insert_rows(
            engine, plan_steps_table, rows, conflict_columns=("step_id",)
        )

    @classmethod
    async def list_steps(cls, engine: Any, plan_id: str) -> list[dict[str, Any]]:
        """Return the steps of a plan, in execution order."""
        await cls.ensure_table(engine)
        async with engine.connect() as conn:
            result = await conn.execute(
                select(plan_steps_table)
                .where(plan_steps_table.c.plan_id == plan_id)
                .order_by(plan_steps_table.c.step_index)
            )
            rows = result.mappings().all()
        return [to_step_response(row) for row in rows]
