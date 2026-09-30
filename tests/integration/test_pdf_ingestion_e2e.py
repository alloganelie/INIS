"""§36.6/§9.1/§11 — un PDF ingéré ressort dans son colis, page par page.

Le critère du lot L2.6 n'est pas « le lecteur sait lire un PDF » (il sait depuis
L2.3) mais « chaque unité extraite d'un PDF sait *où* elle se trouve » : l'unité
d'une page porte son numéro de page, celui du document, jamais une position
supposée. La chaîne exercée ici est la chaîne réelle : ingestion → PostgreSQL →
``PipelineRunner`` → colis §24.1.

Conteneur requis (pgvector) : le test est ignoré sans Docker.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.value_objects.ulid import ULID
from app.knowledge.ingestion.document_ingestor import ingest_document
from app.knowledge.ingestion.request_material import load_request_material
from app.storage.database.engine import create_engine, set_default_engine
from app.storage.database.session import reset_session_maker
from app.storage.repositories.document_repository import DocumentRepository
from app.storage.repositories.information_unit_repository import (
    InformationUnitRepository,
)
from tests.factories import pdf_bytes

OBJECTIVE = "Analyse le rapport PDF fourni"
PAGES = (
    "Paris est la capitale de la France.",
    "Berlin compte trois millions sept cent mille habitants.",
)
STORAGE_REF = "s3://inis-artifacts/documents/REQ_TEST/rapport.pdf"


@pytest.fixture(autouse=True)
def _fresh_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rebuild the process-wide engine in the loop of the current test."""
    monkeypatch.setenv("INIS_NULL_POOL", "1")
    set_default_engine(None)
    reset_session_maker()
    yield
    set_default_engine(None)
    reset_session_maker()


async def _ingest_pdf(engine: Any, request_id: str) -> dict[str, Any]:
    """Ingest one two-page PDF for *request_id*, exactly as the upload does."""
    document_id = ULID.new("DOC_")
    source_id = ULID.new("SRC_")
    outcome = await ingest_document(
        document_id=document_id,
        source_id=source_id,
        request_id=request_id,
        file_name="rapport.pdf",
        mime_type="application/pdf",
        data=pdf_bytes(list(PAGES)),
        storage_ref=STORAGE_REF,
    )
    assert len(outcome.units) == 2, outcome.limitations

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sources (id, url, source_type, data_stage, "
                "created_at, updated_at) VALUES (:id, :url, 'file_upload', 'raw', "
                "now(), now()) ON CONFLICT (id) DO NOTHING"
            ),
            {"id": source_id, "url": f"upload://{document_id}"},
        )
    await DocumentRepository.create(
        engine,
        {
            "document_id": document_id,
            "source_id": source_id,
            "request_id": request_id,
            "file_name": "rapport.pdf",
            "mime_type": "application/pdf",
            "size_bytes": len(pdf_bytes(list(PAGES))),
            "content_hash": "0" * 64,
            "storage_ref": STORAGE_REF,
        },
    )
    for unit in outcome.units:
        await InformationUnitRepository.create(engine, unit)
    return {"document_id": document_id, "source_id": source_id}


def test_each_page_is_persisted_with_its_page_number(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§11 — la position d'une unité est stockée, pas seulement calculée."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)

    async def _run() -> Any:
        engine = create_engine(db_url)
        try:
            request_id = ULID.new("REQ_")
            identifiers = await _ingest_pdf(engine, request_id)
            return identifiers, await load_request_material(request_id)
        finally:
            await engine.dispose()

    identifiers, material = asyncio.run(_run())

    assert len(material.units) == 2
    pages = [unit["location"] for unit in material.units]
    assert all(location["kind"] == "page" for location in pages)
    assert sorted(location["page"] for location in pages) == [1, 2]
    for unit in material.units:
        assert unit["document_id"] == identifiers["document_id"]
        assert unit["provenance"]["extracted_from"] == STORAGE_REF
        assert unit["raw_reference"]["storage_ref"] == STORAGE_REF
    assert material.readers == ["read_pdf"]


def test_the_delivery_of_a_pdf_request_carries_its_pages(
    db_url: str, mock_llm: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§24.1/§12.1 — les pages du PDF arrivent dans le colis, avec leur lignage."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    mock_llm.configure('{"summary": "Rapport lu.", "findings": []}')
    search = AsyncMock(return_value=[])
    monkeypatch.setattr("app.connectors.web.provider_router.ProviderRouter.search", search)

    async def _run() -> dict[str, Any]:
        engine = create_engine(db_url)
        try:
            request_id = ULID.new("REQ_")
            identifiers = await _ingest_pdf(engine, request_id)
            delivery = await PipelineRunner().run(
                request_id, {"objective": OBJECTIVE, "request_type": "data"}
            )
            return {**identifiers, "delivery": delivery}
        finally:
            await engine.dispose()

    scenario = asyncio.run(_run())
    delivery = scenario["delivery"]

    # §7 — a request whose source is its own file does not search the web for it.
    assert search.await_count == 0

    units = [
        unit
        for unit in delivery["information_units"]
        if unit.get("document_id") == scenario["document_id"]
    ]
    assert sorted(unit["location"]["page"] for unit in units) == [1, 2]
    assert {unit["content"]["text"] for unit in units} == set(PAGES)

    stages = [
        (item["parameters"]["stage"], item["tool"]) for item in delivery["transformations"]
    ]
    assert ("raw", "read_pdf") in stages
    assert ("normalized", "DocumentIngestor.ingest") in stages
