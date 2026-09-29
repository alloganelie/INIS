"""Integration tests for pipeline PostgreSQL persistence per §0.2, §12, §20, §27.

Acceptance criteria of B4-bis Constat 1:
- test_pipeline_persists_audit_event_to_db (testcontainers Postgres)
- test_pipeline_persists_information_units_to_db
- test_pipeline_uses_get_session_transaction
- test_pipeline_marks_in_memory_limitation_without_db
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.value_objects.ulid import ULID
from app.storage.database.engine import create_engine
from app.storage.database.session import reset_session_maker


@pytest.mark.asyncio
async def test_pipeline_marks_in_memory_limitation_without_db(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without INIS_DATABASE_URL the pipeline delivers but marks the limitation."""
    monkeypatch.delenv("INIS_DATABASE_URL", raising=False)
    reset_session_maker()

    runner = PipelineRunner()
    req_id = ULID.new("REQ_")
    result = await runner.run(req_id, {"objective": "offline check"})

    assert any("in-memory only" in lim for lim in result["limitations"])
    assert result["audit"]["persisted"] is False
    assert result["audit"]["audit_id"].startswith("AUD_")


@pytest.mark.asyncio
async def test_pipeline_persists_audit_event_to_db(db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """With INIS_DATABASE_URL set, a real audit_event row is inserted via AuditWriter."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    reset_session_maker()

    runner = PipelineRunner()
    req_id = ULID.new("REQ_")
    result = await runner.run(req_id, {"objective": "persisted audit event"})

    assert result["audit"]["persisted"] is True
    audit_id = result["audit"]["audit_id"]

    engine = create_engine(db_url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text("SELECT id, actor_type, resource_id, result FROM audit_events WHERE id = :id"),
                    {"id": audit_id},
                )
            ).mappings().first()
    finally:
        await engine.dispose()

    assert row is not None
    assert row["id"] == audit_id
    assert row["actor_type"] == "pipeline"
    assert row["resource_id"] == req_id


@pytest.mark.asyncio
async def test_pipeline_persists_information_units_to_db(db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """With INIS_DATABASE_URL set, information_units and evidence are written to tables."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    reset_session_maker()

    runner = PipelineRunner()
    req_id = ULID.new("REQ_")
    result = await runner.run(req_id, {"objective": "persisted units and evidence"})

    assert result["audit"]["persisted"] is True
    assert len(result["information_units"]) >= 1
    inf_id = result["information_units"][0]["information_id"]

    engine = create_engine(db_url)
    try:
        async with engine.connect() as conn:
            unit_row = (
                await conn.execute(
                    text("SELECT id, type, source_id, data_stage FROM information_units WHERE id = :id"),
                    {"id": inf_id},
                )
            ).mappings().first()
            ev_count = (
                await conn.execute(
                    text("SELECT count(*) FROM evidence WHERE information_id = :id"),
                    {"id": inf_id},
                )
            ).scalar_one()
            trf_rows = (
                await conn.execute(
                    text(
                        "SELECT parameters->>'stage' AS stage FROM transformations "
                        "WHERE justification LIKE :just"
                    ),
                    {"just": f"%{req_id}%"},
                )
            ).mappings().all()
    finally:
        await engine.dispose()

    assert unit_row is not None
    assert unit_row["id"] == inf_id
    assert ev_count >= 1
    # §12.1 — one transformation per stage the run really executed, not a single
    # generic TRF_ row (C11): the stages are readable from the row itself.
    stages = {row["stage"] for row in trf_rows}
    assert {"raw", "normalized"} <= stages
    assert len(trf_rows) == len(stages), "one row per stage, no duplicate stage"


@pytest.mark.asyncio
async def test_pipeline_uses_get_session_transaction(db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """The pipeline calls get_session() — the orphaned session provider is now live."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    reset_session_maker()

    import app.storage.database.session as session_module

    original_get_session = session_module.get_session
    call_count = 0

    async def _spied_get_session():
        nonlocal call_count
        call_count += 1
        async for s in original_get_session():
            yield s

    monkeypatch.setattr(session_module, "get_session", _spied_get_session)

    runner = PipelineRunner()
    req_id = ULID.new("REQ_")
    result = await runner.run(req_id, {"objective": "session transaction check"})

    assert result["audit"]["persisted"] is True
    assert call_count >= 1, "get_session() must be called for the pipeline transaction"
