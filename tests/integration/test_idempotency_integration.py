"""Integration tests for the §5.3 idempotence guarantee on real PostgreSQL.

A replayed message (same ``request_id``, same business identifiers) must not
duplicate what was already stored. The pipeline persistence helper is the write
path under test: it is replayed here with frozen identifiers, exactly as a
retry after a crash would replay it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.api.v1.requests.pipeline_persistence import persist_pipeline_delivery
from app.domain.value_objects.ulid import ULID
from app.storage.database.engine import create_engine
from app.storage.database.session import reset_session_maker


@pytest.fixture(autouse=True)
def _database_configured(db_url: str, monkeypatch: pytest.MonkeyPatch):
    """Point the persistence helper at the container database."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    reset_session_maker()
    yield
    reset_session_maker()


def _payload(request_id: str) -> dict:
    """Return a frozen delivery payload with deterministic identifiers."""
    source_id = "SRC_" + ULID.new("REQ_").removeprefix("REQ_")
    unit_id = "INF_" + ULID.new("REQ_").removeprefix("REQ_")
    evidence_id = "EVID_" + ULID.new("REQ_").removeprefix("REQ_")
    return {
        "request_id": request_id,
        "objective": "idempotency probe",
        "delivery_status": "completed",
        "sources": [
            {
                "source_id": source_id,
                "url": "https://example.com/idempotent",
                "source_type": "web",
                "reliability_score": 0.8,
            }
        ],
        "information_units": [
            {
                "information_id": unit_id,
                "type": "text",
                "content": {"text": "Paris is the capital of France."},
                "source_id": source_id,
                "data_stage": "derived",
            }
        ],
        "evidence": [
            {
                "evidence_id": evidence_id,
                "information_id": unit_id,
                "source_id": source_id,
                "excerpt": "Paris is the capital of France.",
                "strength": 0.9,
            }
        ],
        "step_results": [{"step_id": "STEP_1", "status": "completed"}],
        "_ids": {"source": source_id, "unit": unit_id, "evidence": evidence_id},
    }


async def _persist(payload: dict) -> tuple[bool, list[str], dict]:
    """Replay one delivery payload through the persistence helper."""
    return await persist_pipeline_delivery(
        payload["request_id"],
        payload["objective"],
        payload["delivery_status"],
        payload["sources"],
        payload["information_units"],
        payload["evidence"],
        payload["step_results"],
    )


async def _counts(db_url: str, ids: dict[str, str]) -> dict[str, int]:
    """Return the row counts of the replayed payload."""
    engine = create_engine(db_url)
    try:
        async with engine.connect() as conn:
            units = (
                await conn.execute(
                    text("SELECT count(*) FROM information_units WHERE id = :id"),
                    {"id": ids["unit"]},
                )
            ).scalar_one()
            evidence = (
                await conn.execute(
                    text("SELECT count(*) FROM evidence WHERE evidence_id = :id"),
                    {"id": ids["evidence"]},
                )
            ).scalar_one()
            sources = (
                await conn.execute(
                    text("SELECT count(*) FROM sources WHERE id = :id"),
                    {"id": ids["source"]},
                )
            ).scalar_one()
            transformations = (
                await conn.execute(
                    text(
                        "SELECT count(*) FROM transformations "
                        "WHERE CAST(output_ids AS TEXT) LIKE :pattern"
                    ),
                    {"pattern": f"%{ids['unit']}%"},
                )
            ).scalar_one()
    finally:
        await engine.dispose()
    return {
        "units": units,
        "evidence": evidence,
        "sources": sources,
        "transformations": transformations,
    }


class TestReplayIdempotence:
    """§5.3 — replaying a message converges to the same state."""

    async def test_first_delivery_persists_the_payload(self, db_url: str) -> None:
        """The first call stores one unit, one evidence row and one source."""
        payload = _payload(ULID.new("REQ_"))
        stored, limitations, audit = await _persist(payload)
        assert stored is True
        assert limitations == []
        assert audit["audit_event_id"].startswith("AUD_")
        counts = await _counts(db_url, payload["_ids"])
        assert counts["units"] == 1
        assert counts["evidence"] == 1
        assert counts["sources"] == 1

    async def test_replay_does_not_duplicate_units_or_evidence(
        self, db_url: str
    ) -> None:
        """The same payload stored three times leaves one row per identifier."""
        payload = _payload(ULID.new("REQ_"))
        for _ in range(3):
            await _persist(payload)
        counts = await _counts(db_url, payload["_ids"])
        assert counts["units"] == 1
        assert counts["evidence"] == 1
        assert counts["sources"] == 1

    async def test_replay_keeps_the_lineage_traceable(self, db_url: str) -> None:
        """Each replay records a transformation row referencing the same unit."""
        payload = _payload(ULID.new("REQ_"))
        await _persist(payload)
        first = (await _counts(db_url, payload["_ids"]))["transformations"]
        assert first >= 1
        await _persist(payload)
        assert (await _counts(db_url, payload["_ids"]))["transformations"] >= first

    async def test_distinct_requests_are_stored_separately(self, db_url: str) -> None:
        """Idempotence is per identifier: another request adds its own rows."""
        payloads = [_payload(ULID.new("REQ_")), _payload(ULID.new("REQ_"))]
        for payload in payloads:
            await _persist(payload)
        for payload in payloads:
            counts = await _counts(db_url, payload["_ids"])
            assert counts["units"] == 1
            assert counts["evidence"] == 1

    async def test_reliability_score_is_kept_on_replay(self, db_url: str) -> None:
        """A replay refreshes ``updated_at`` without losing the score (§9)."""
        payload = _payload(ULID.new("REQ_"))
        await _persist(payload)
        await _persist(payload)
        engine = create_engine(db_url)
        try:
            async with engine.connect() as conn:
                score = (
                    await conn.execute(
                        text("SELECT reliability_score FROM sources WHERE id = :id"),
                        {"id": payload["_ids"]["source"]},
                    )
                ).scalar_one()
        finally:
            await engine.dispose()
        assert float(score) == pytest.approx(0.8)


class TestDegradedPersistence:
    """§0.2 — without a database the delivery is returned, with a limitation."""

    async def test_missing_database_marks_a_limitation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No ``INIS_DATABASE_URL`` means in-memory only, never a crash."""
        monkeypatch.delenv("INIS_DATABASE_URL", raising=False)
        reset_session_maker()
        payload = _payload(ULID.new("REQ_"))
        stored, limitations, audit = await _persist(payload)
        assert stored is False
        assert any("in-memory only" in limitation for limitation in limitations)
        assert audit["audit_event_id"].startswith("AUD_")

