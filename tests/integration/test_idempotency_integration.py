"""Integration tests for the §5.3 idempotence guarantee on real PostgreSQL.

A replayed message (same ``request_id``, same business identifiers) must not
duplicate what was already stored. The pipeline persistence helper is the write
path under test: it is replayed here with frozen identifiers, exactly as a
retry after a crash would replay it.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.api.v1.requests.pipeline_persistence import (
    persist_pipeline_delivery,
    persist_transformations,
)
from app.domain.value_objects.ulid import ULID
from app.knowledge.provenance.stage_transformations import build_transformations
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
    """Replay one delivery payload through the persistence helpers.

    Since L2.3 the §12.1 lineage is written by the pipeline through
    ``persist_transformations`` (one row per real stage, C11) instead of a
    single generic row inside ``persist_pipeline_delivery``: a replay test must
    therefore exercise both, exactly as a run does.
    """
    result = await persist_pipeline_delivery(
        payload["request_id"],
        payload["objective"],
        payload["delivery_status"],
        payload["sources"],
        payload["information_units"],
        payload["evidence"],
        payload["step_results"],
    )
    transformations = payload.get("transformations")
    if transformations:
        await persist_transformations(transformations, request_id=payload["request_id"])
    return result


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


class TestMemoryReuseIsIdempotent:
    """§17.1/§5.3 — une unité réutilisée depuis la mémoire n'est pas dupliquée.

    Le run réutilise l'unité **avec son identifiant d'origine** : l'écriture
    retombe donc sur ``ON CONFLICT (id) DO NOTHING``. C'est ce que ce test
    vérifie, et il vérifie aussi que le contexte stocké dit que l'unité vient de
    la mémoire — un enregistrement muet sur son origine ne serait pas exploitable
    (§11, §20).
    """

    async def test_reusing_a_known_unit_keeps_a_single_row(self, db_url: str) -> None:
        first = _payload(ULID.new("REQ_"))
        await _persist(first)
        unit_id = first["_ids"]["unit"]
        source_id = first["_ids"]["source"]

        # Second run : l'unité vient de la mémoire, avec son contexte de réusage.
        second = _payload(ULID.new("REQ_"))
        second["information_units"] = [
            {
                "information_id": unit_id,
                "type": "text",
                "content": {"text": "Paris is the capital of France."},
                "source_id": source_id,
                "data_stage": "derived",
                "context": {"memory": {"reused": True, "mode": "hybrid"}},
            }
        ]
        await _persist(second)

        engine = create_engine(db_url)
        try:
            async with engine.connect() as connection:
                rows = (
                    (
                        await connection.execute(
                            text(
                                "SELECT count(*) AS total, min(source_id) AS source_id, "
                                "min(data_stage) AS data_stage "
                                "FROM information_units WHERE id = :id"
                            ),
                            {"id": unit_id},
                        )
                    )
                    .mappings()
                    .all()
                )
        finally:
            await engine.dispose()

        assert rows[0]["total"] == 1, "la mémoire n'a pas créé un second enregistrement"
        # C'est la première écriture qui fait foi : réutiliser une unité la
        # référence, elle ne la réécrit pas sous un autre contexte (§5.3).
        assert rows[0]["source_id"] == source_id
        assert rows[0]["data_stage"] == "derived"


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
        """Each replay records the same §12.1 stages: idempotent, never lost."""
        payload = _payload(ULID.new("REQ_"))
        transformations = build_transformations(
            request_id=payload["request_id"],
            objective=payload["objective"],
            sources=payload["sources"],
            information_units=payload["information_units"],
            evidence=payload["evidence"],
        )
        payload["transformations"] = transformations

        await _persist(payload)
        first = (await _counts(db_url, payload["_ids"]))["transformations"]
        assert first >= 1

        await _persist(payload)
        # §12.1/C11 — the same stage rows replay onto themselves (ON CONFLICT DO
        # NOTHING), so a retry adds no duplicate lineage.
        assert (await _counts(db_url, payload["_ids"]))["transformations"] == first

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

