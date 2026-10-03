"""§17.1/§20 — l'arrêt d'acquisition est écrit dans la piste d'audit, en base.

La décision d'arrêter l'acquisition est une décision de gouvernance : elle doit
se relire après coup. Ce test la fait tourner contre le **vrai** PostgreSQL et
relit la ligne ``audit_events`` produite — la décision est donc dans la base, pas
seulement dans la réponse HTTP.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.value_objects.ulid import ULID
from app.storage.database.engine import create_engine
from app.storage.database.session import reset_session_maker
from tests.unit.planning.test_memory_checker_wired_in_pipeline import (
    OBJECTIVE,
    UNIT_ID,
    FakeMemorySearch,
    _install_search,
)


@pytest.fixture(autouse=True)
def _no_web(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le fournisseur web ne doit pas être appelé : la mémoire suffit."""
    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.connectors.web.extractors.wikipedia_extractor.WikipediaExtractor.extract",
        AsyncMock(return_value={}),
    )


@pytest.mark.asyncio
async def test_the_early_stop_is_written_to_the_audit_trail(
    db_url: str, mock_llm: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Une mémoire suffisante (hybride) laisse une trace d'arrêt en base."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    reset_session_maker()
    _install_search(monkeypatch, FakeMemorySearch())

    request_id = ULID.new("REQ_")
    delivery = await PipelineRunner().run(
        request_id, {"objective": OBJECTIVE, "request_type": "research"}
    )

    assert delivery["provenance"]["memory"]["stopped_acquisition"] is True

    engine = create_engine(db_url)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT action, result, reason, resource_id FROM audit_events "
                        "WHERE request_id = :rid AND action = 'memory_lookup'"
                    ),
                    {"rid": request_id},
                )
            ).mappings().all()
    finally:
        await engine.dispose()

    assert len(rows) == 1, f"un événement d'audit attendu, trouvé {len(rows)}"
    event = rows[0]
    assert event["result"] == "success"
    assert event["resource_id"] == UNIT_ID
    assert "acquisition arrêtée" in event["reason"]
    assert "provenance_complete" in event["reason"]


@pytest.mark.asyncio
async def test_a_normal_run_writes_no_stop_claim(
    db_url: str, mock_llm: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le cas négatif, relu en base : aucune trace d'arrêt quand la mémoire manque."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    reset_session_maker()
    _install_search(monkeypatch, FakeMemorySearch(sufficient=False))

    request_id = ULID.new("REQ_")
    delivery = await PipelineRunner().run(
        request_id, {"objective": OBJECTIVE, "request_type": "research"}
    )

    assert delivery["provenance"]["memory"]["stopped_acquisition"] is False

    engine = create_engine(db_url)
    try:
        async with engine.connect() as conn:
            reasons = (
                await conn.execute(
                    text(
                        "SELECT reason FROM audit_events "
                        "WHERE request_id = :rid AND action = 'memory_lookup'"
                    ),
                    {"rid": request_id},
                )
            ).scalars().all()
    finally:
        await engine.dispose()

    assert reasons, "l'événement d'audit doit exister même sans réutilisation"
    assert all("acquisition arrêtée" not in str(reason) for reason in reasons)
