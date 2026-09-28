"""Tests for the shared fixtures of :mod:`tests.conftest` (§33.2).

These tests double as the acceptance criteria of B4-bis constat 5: the
database fixture must provide a *migrated* PostgreSQL, the Redis fixture must
provide a usable endpoint, the ``PipelineRunner`` singleton must be isolated
between tests, and the LLM/Web doubles must be reusable instead of
copy-pasted.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.mark.asyncio
async def test_conftest_db_fixture_provides_working_postgres(db_url: str) -> None:
    """The ``db_url`` fixture yields a live PostgreSQL with the §27 schema."""
    from sqlalchemy import text

    from app.storage.database.engine import create_engine

    engine = create_engine(db_url)
    try:
        async with engine.connect() as connection:
            assert (await connection.execute(text("SELECT 1"))).scalar_one() == 1
            rows = await connection.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            )
        tables = {row[0] for row in rows}
    finally:
        await engine.dispose()

    assert db_url.startswith("postgresql+asyncpg://")
    # The migrations — not a hand-made metadata.create_all — created these.
    assert {"audit_events", "information_units", "evidence", "sources"} <= tables
    assert "alembic_version" in tables


@pytest.mark.asyncio
async def test_conftest_redis_fixture_provides_working_redis(redis_url: str) -> None:
    """The ``redis_url`` fixture yields a reachable Redis endpoint."""
    redis_asyncio = pytest.importorskip("redis.asyncio")

    client = redis_asyncio.from_url(redis_url)
    try:
        assert await client.ping() is True
        await client.set("inis:b4bis:fixture", "ok", ex=10)
        assert await client.get("inis:b4bis:fixture") == b"ok"
    finally:
        await client.aclose()


def test_pipeline_state_reset_between_tests_part_one_pollutes() -> None:
    """First half of the isolation check: pollute the singleton on purpose."""
    from app.api.v1.requests.pipeline_runner import pipeline_runner

    pipeline_runner._run_states["REQ_LEAKED"] = {"status": "processing"}
    pipeline_runner._event_history["REQ_LEAKED"] = [{"step": "started"}]
    pipeline_runner._runs_count = 7

    assert pipeline_runner.get_state("REQ_LEAKED") is not None


def test_pipeline_state_reset_between_tests_part_two_is_clean() -> None:
    """Second half: the autouse fixture wiped the previous test's state."""
    from app.api.v1.requests.pipeline_runner import pipeline_runner

    assert pipeline_runner.get_state("REQ_LEAKED") is None
    assert pipeline_runner._event_history == {}
    assert pipeline_runner._runs_count == 0
    assert pipeline_runner.is_running("REQ_LEAKED") is False


@pytest.mark.asyncio
async def test_mock_llm_fixture_is_configurable(mock_llm: Any) -> None:
    """``mock_llm`` returns the configured content and records the calls."""
    from app.llm.router.model_router import LLMTask, ModelRouter

    mock_llm.configure('{"summary": "ok", "findings": []}')

    response = await ModelRouter().complete(LLMTask(task_type="understanding"), "prompt")

    assert response.content == '{"summary": "ok", "findings": []}'
    assert response.stub is False
    assert len(mock_llm.calls) == 1


@pytest.mark.asyncio
async def test_mock_web_fixture_answers_wikipedia(mock_web: Any) -> None:
    """``mock_web`` makes the real §9/§10 connectors run offline."""
    import httpx

    async with httpx.AsyncClient(timeout=1.0) as client:
        response = await client.get(
            "https://fr.wikipedia.org/w/api.php?action=opensearch&search=Paris"
        )

    assert response.status_code == 200
    assert response.json()[0] == "Paris"
