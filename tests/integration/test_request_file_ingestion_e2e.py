"""§36.6/§24.1 — critère de sortie L2 : un CSV ingéré ressort dans le colis.

La chaîne exercée est celle qui manquait : un CSV est ingéré pour une requête
(unités §11 + ``Dataset`` persistés, chemin du lot L2.3), puis ``PipelineRunner``
tourne contre le **vrai** PostgreSQL et son colis doit contenir les ``datasets[]``
du fichier, ses unités localisables, les transformations §12.1 de l'ingestion et
une provenance complète — sans chercher sur le web ce que la requête a fourni
(§7, C4).

Le téléversement HTTP multipart (objet S3, endpoints, classification PII) est
couvert par ``tests/integration/test_document_upload_s3.py`` : ici on isole le
chaînon qui manquait entre l'ingestion et la livraison.

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
from app.storage.repositories.dataset_repository import DatasetRepository
from app.storage.repositories.document_repository import DocumentRepository
from app.storage.repositories.information_unit_repository import (
    InformationUnitRepository,
)

OBJECTIVE = "Analyse le fichier de population fourni"
CSV_BYTES = b"city,population\nParis,2145906\nBerlin,3645000\n"
STORAGE_REF = "s3://inis-artifacts/documents/REQ_TEST/csv-digest.csv"


@pytest.fixture(autouse=True)
def _fresh_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rebuild the process-wide engine in the loop of the current test."""
    monkeypatch.setenv("INIS_NULL_POOL", "1")
    set_default_engine(None)
    reset_session_maker()
    yield
    set_default_engine(None)
    reset_session_maker()


def _stages(delivery: dict[str, Any]) -> list[tuple[str, str]]:
    """Return the (stage, tool) pairs of the delivered §12.1 transformations."""
    return [
        (item["parameters"]["stage"], item["tool"])
        for item in delivery["transformations"]
    ]


def _file_units(delivery: dict[str, Any], document_id: str) -> list[dict[str, Any]]:
    """Return the delivered units that came from *document_id*."""
    return [
        unit
        for unit in delivery["information_units"]
        if unit.get("document_id") == document_id
    ]
async def _ingest_csv(engine: Any, request_id: str) -> dict[str, str]:
    """Ingest one CSV for *request_id* exactly as the upload endpoint does.

    The bytes are not pushed to S3 here (that path is covered by
    ``test_document_upload_s3.py``): what matters is that the §11 units and the
    ``Dataset`` land in PostgreSQL under the request's identifier, because that
    is what the pipeline reads back.
    """
    document_id = ULID.new("DOC_")
    source_id = ULID.new("SRC_")
    outcome = ingest_document(
        document_id=document_id,
        source_id=source_id,
        request_id=request_id,
        file_name="villes.csv",
        mime_type="text/csv",
        data=CSV_BYTES,
        storage_ref=STORAGE_REF,
    )
    assert outcome.dataset is not None
    assert len(outcome.units) == 2

    # §9.1 — the document points at a real ``sources`` row, as the upload does.
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
            "file_name": "villes.csv",
            "mime_type": "text/csv",
            "size_bytes": len(CSV_BYTES),
            "content_hash": "0" * 64,
            "storage_ref": STORAGE_REF,
        },
    )
    await DatasetRepository.create(
        engine,
        {**outcome.dataset, "name": "villes.csv", "request_id": request_id},
    )
    for unit in outcome.units:
        await InformationUnitRepository.create(engine, unit)
    return {
        "document_id": document_id,
        "source_id": source_id,
        "dataset_id": str(outcome.dataset["dataset_id"]),
    }


async def _run_scenario(db_url: str, request_type: str = "data") -> dict[str, Any]:
    """Ingest a CSV for a fresh request, run the pipeline, return what happened."""
    engine = create_engine(db_url)
    try:
        request_id = ULID.new("REQ_")
        identifiers = await _ingest_csv(engine, request_id)
        delivery = await PipelineRunner().run(
            request_id, {"objective": OBJECTIVE, "request_type": request_type}
        )
        return {"request_id": request_id, **identifiers, "delivery": delivery}
    finally:
        await engine.dispose()

def test_the_delivery_of_a_data_request_carries_its_csv(
    db_url: str, mock_llm: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§24.1 — ``datasets[]`` non vide, unités localisables, lignage complet."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    mock_llm.configure('{"summary": "Fichier ingéré.", "findings": []}')

    scenario = asyncio.run(_run_scenario(db_url, "data"))
    delivery = scenario["delivery"]
    document_id = scenario["document_id"]

    # §24.1 — the dataset of the ingested file is delivered, not dropped.
    assert len(delivery["datasets"]) == 1
    dataset = delivery["datasets"][0]
    assert dataset["dataset_id"] == scenario["dataset_id"]
    assert dataset["row_count"] == 2
    assert dataset["storage_ref"] == STORAGE_REF

    # §11 — each unit locates itself in the file, and points back at its dataset.
    units = _file_units(delivery, document_id)
    assert len(units) == 2
    assert {unit["dataset_id"] for unit in units} == {scenario["dataset_id"]}
    assert sorted(unit["location"]["row"] for unit in units) == [1, 2]
    for unit in units:
        assert unit["location"]["kind"] == "row"
        assert unit["provenance"]["extracted_from"] == STORAGE_REF
        assert unit["source_id"] == scenario["source_id"]

    # §9.1 — the document is a source of the colis.
    source_ids = {source["source_id"] for source in delivery["sources"]}
    assert scenario["source_id"] in source_ids

    # §12.1 — the ingestion is a stage of its own, with the reader that ran.
    stages = _stages(delivery)
    assert ("raw", "read_csv") in stages
    assert ("normalized", "DocumentIngestor.ingest") in stages

    # §7 — the request type is stated in the provenance.
    assert delivery["provenance"]["request_type"] == "data"


def test_a_data_request_does_not_search_the_web_for_its_own_file(
    db_url: str, mock_llm: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§7/§8.4 — « data » : la source est le fichier, pas une recherche."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    mock_llm.configure('{"summary": "Fichier ingéré.", "findings": []}')
    search = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search", search
    )

    scenario = asyncio.run(_run_scenario(db_url, "data"))

    assert search.await_count == 0
    assert len(scenario["delivery"]["datasets"]) == 1

def test_the_material_is_read_from_postgres_not_guessed(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§9.1 — la matière relue est celle réellement stockée, pas une convention."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)

    async def _read_material() -> tuple[dict[str, str], Any]:
        engine = create_engine(db_url)
        try:
            request_id = ULID.new("REQ_")
            identifiers = await _ingest_csv(engine, request_id)
            return identifiers, await load_request_material(request_id)
        finally:
            await engine.dispose()

    identifiers, material = asyncio.run(_read_material())

    assert [document["document_id"] for document in material.documents] == [
        identifiers["document_id"]
    ]
    assert len(material.datasets) == 1
    assert material.datasets[0]["dataset_id"] == identifiers["dataset_id"]
    assert material.datasets[0]["row_count"] == 2
    assert material.datasets[0]["storage_ref"] == STORAGE_REF
    assert len(material.units) == 2
    assert material.readers == ["read_csv"]
    assert material.limitations == []
    assert all(unit["location"]["kind"] == "row" for unit in material.units)
    assert {unit["dataset_id"] for unit in material.units} == {
        identifiers["dataset_id"]
    }


def test_reading_the_material_twice_changes_nothing(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§5.3/§9.1 — relire la matière est une lecture : aucun doublon créé."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)

    async def _read_twice() -> tuple[Any, int]:
        engine = create_engine(db_url)
        try:
            request_id = ULID.new("REQ_")
            await _ingest_csv(engine, request_id)
            before = await load_request_material(request_id)
            await load_request_material(request_id)
            async with engine.connect() as conn:
                row = (
                    await conn.execute(
                        text(
                            "SELECT count(*) AS total FROM information_units "
                            "WHERE document_id IN ("
                            "SELECT id FROM documents WHERE request_id = :rid)"
                        ),
                        {"rid": request_id},
                    )
                ).mappings().first()
            return before, int((row or {}).get("total") or 0)
        finally:
            await engine.dispose()

    before, count = asyncio.run(_read_twice())

    assert len(before.units) == 2
    assert count == len(before.units)

