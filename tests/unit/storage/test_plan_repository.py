"""Unit tests of ``PlanRepository`` (§8, §27, L6.2).

Revision ``0007`` created ``plans`` / ``plan_steps``; before this repository the
planner kept its plan in the process, so a restart lost the steps a request had
executed. These tests pin the round trip and the ordering the plan relies on.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.storage.database.engine import create_engine
from app.storage.repositories.plan_repository import (
    PlanRepository,
    plan_steps_table,
    plans_table,
)


@pytest.fixture
async def engine(tmp_path: Path) -> AsyncIterator[object]:
    """A disposable SQLite engine (the PostgreSQL schema is Alembic's)."""
    built = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'plans.db'}")
    try:
        yield built
    finally:
        await built.dispose()


def test_tables_mirror_revision_0007() -> None:
    """Both tables declare exactly the columns revision 0007 created."""
    assert set(plans_table.columns.keys()) == {
        "plan_id",
        "request_id",
        "status",
        "objective",
        "created_at",
    }
    assert set(plan_steps_table.columns.keys()) == {
        "step_id",
        "plan_id",
        "step_index",
        "action",
        "tool",
        "status",
        "inputs",
        "result",
    }


@pytest.mark.asyncio
async def test_create_then_get(engine: object) -> None:
    """A created plan keeps the identifier it was given."""
    created = await PlanRepository.create(
        engine,
        {
            "plan_id": "PLAN_L6_1",
            "request_id": "REQ_L6_1",
            "objective": "vérifier la persistance",
        },
    )
    assert created["plan_id"] == "PLAN_L6_1"
    assert created["status"] == "draft"

    stored = await PlanRepository.get(engine, "PLAN_L6_1")
    assert stored is not None
    assert stored["objective"] == "vérifier la persistance"
    assert await PlanRepository.get(engine, "PLAN_ABSENT") is None


@pytest.mark.asyncio
async def test_generated_identifier_when_absent(engine: object) -> None:
    """A caller without an identifier gets a new ``PLAN_`` one."""
    created = await PlanRepository.create(engine, {"request_id": "REQ_L6_2"})
    assert str(created["plan_id"]).startswith("PLAN_")


@pytest.mark.asyncio
async def test_list_for_request_is_filtered(engine: object) -> None:
    """Only the plans of the asked request come back."""
    await PlanRepository.create(engine, {"plan_id": "PLAN_L6_A", "request_id": "REQ_L6_A"})
    await PlanRepository.create(engine, {"plan_id": "PLAN_L6_B", "request_id": "REQ_L6_B"})
    found = await PlanRepository.list_for_request(engine, "REQ_L6_B")
    assert [plan["plan_id"] for plan in found] == ["PLAN_L6_B"]


@pytest.mark.asyncio
async def test_steps_keep_their_execution_order(engine: object) -> None:
    """``step_index`` defaults to the order the steps were given in."""
    await PlanRepository.create(engine, {"plan_id": "PLAN_L6_C", "request_id": "REQ_L6_C"})
    written = await PlanRepository.add_steps(
        engine,
        "PLAN_L6_C",
        [
            {"action": "parse_request", "tool": "understand_request"},
            {"action": "search", "tool": "web_search", "inputs": {"q": "inis"}},
            {"action": "synthesize", "tool": "synthesize"},
        ],
    )
    assert written == 3

    steps = await PlanRepository.list_steps(engine, "PLAN_L6_C")
    assert [step["step_index"] for step in steps] == [1, 2, 3]
    assert steps[1]["inputs"] == {"q": "inis"}
    assert steps[0]["status"] == "pending"


@pytest.mark.asyncio
async def test_update_status_is_durable(engine: object) -> None:
    """A plan status change is readable on a fresh read."""
    await PlanRepository.create(engine, {"plan_id": "PLAN_L6_D", "request_id": "REQ_L6_D"})
    await PlanRepository.update_status(engine, "PLAN_L6_D", "executed")
    stored = await PlanRepository.get(engine, "PLAN_L6_D")
    assert stored is not None
    assert stored["status"] == "executed"
