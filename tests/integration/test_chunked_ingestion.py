"""ADR 007/§41.6 — l'ingestion d'un gros fichier passe vraiment par les tronçons.

Le processeur §41.6 existait, testé, et **aucun chemin réel ne l'atteignait** :
l'ingestion lisait le document entier. Ce test exerce le seuil de l'ADR 007 de
bout en bout, contre le vrai PostgreSQL : un CSV de plus de 50 enregistrements est
découpé, chaque tronçon produit ses unités §11, et toutes se retrouvent en base —
dans l'ordre du fichier, avec leur dataset.

Conteneur requis (pgvector) : le test est ignoré sans Docker.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import text

from app.domain.value_objects.ulid import ULID
from app.knowledge.ingestion import document_ingestor
from app.knowledge.ingestion.document_ingestor import ingest_document
from app.knowledge.ingestion.request_material import load_request_material
from app.knowledge.normalization.chunked_dataset import DefaultChunkedDatasetProcessor
from app.knowledge.normalization.limits import MAX_INFORMATION_UNITS_PER_REQUEST_ENV
from app.storage.database.engine import create_engine, set_default_engine
from app.storage.database.session import reset_session_maker
from app.storage.repositories.dataset_repository import DatasetRepository
from app.storage.repositories.document_repository import DocumentRepository
from app.storage.repositories.information_unit_repository import (
    InformationUnitRepository,
)

ROW_COUNT = 120
STORAGE_REF = "s3://inis-artifacts/documents/REQ_TEST/gros.csv"
CSV_BYTES = (
    "\n".join(
        ["city,population"] + [f"ville{i},{i * 1000}" for i in range(1, ROW_COUNT + 1)]
    )
    + "\n"
).encode("utf-8")


class _RecordingProcessor(DefaultChunkedDatasetProcessor):
    """The §41.6 processor of the run, kept aside to inspect its chunks."""

    last: _RecordingProcessor | None = None

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.chunk_sizes: list[int] = []
        _RecordingProcessor.last = self

    async def process_chunk(self, chunk: Any) -> Any:  # type: ignore[override]
        self.chunk_sizes.append(len(chunk.rows))
        return await super().process_chunk(chunk)


@pytest.fixture(autouse=True)
def _fresh_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rebuild the process-wide engine in the loop of the current test."""
    monkeypatch.setenv("INIS_NULL_POOL", "1")
    set_default_engine(None)
    reset_session_maker()
    yield
    set_default_engine(None)
    reset_session_maker()


def test_a_payload_beyond_the_threshold_is_ingested_by_chunks(
    db_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§41.6 — les unités se construisent par tronçons, et toutes sont persistées."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    monkeypatch.setenv(MAX_INFORMATION_UNITS_PER_REQUEST_ENV, "50")
    monkeypatch.setattr(
        document_ingestor, "DefaultChunkedDatasetProcessor", _RecordingProcessor
    )

    async def _run() -> tuple[Any, int]:
        engine = create_engine(db_url)
        try:
            request_id = ULID.new("REQ_")
            document_id = ULID.new("DOC_")
            source_id = ULID.new("SRC_")
            outcome = await ingest_document(
                document_id=document_id,
                source_id=source_id,
                request_id=request_id,
                file_name="gros.csv",
                mime_type="text/csv",
                data=CSV_BYTES,
                storage_ref=STORAGE_REF,
            )
            assert outcome.dataset is not None

            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "INSERT INTO sources (id, url, source_type, data_stage, "
                        "created_at, updated_at) VALUES (:id, :url, 'file_upload', "
                        "'raw', now(), now()) ON CONFLICT (id) DO NOTHING"
                    ),
                    {"id": source_id, "url": f"upload://{document_id}"},
                )
            await DocumentRepository.create(
                engine,
                {
                    "document_id": document_id,
                    "source_id": source_id,
                    "request_id": request_id,
                    "file_name": "gros.csv",
                    "mime_type": "text/csv",
                    "size_bytes": len(CSV_BYTES),
                    "content_hash": "0" * 64,
                    "storage_ref": STORAGE_REF,
                },
            )
            await DatasetRepository.create(
                engine,
                {**outcome.dataset, "name": "gros.csv", "request_id": request_id},
            )
            for unit in outcome.units:
                await InformationUnitRepository.create(engine, unit)

            material = await load_request_material(request_id)
            return outcome, len(material.units)
        finally:
            await engine.dispose()

    outcome, persisted = asyncio.run(_run())

    # §41.6 — three chunks of at most 50 rows, never more.
    processor = _RecordingProcessor.last
    assert processor is not None
    assert processor.chunk_sizes == [50, 50, 20]
    assert max(processor.chunk_sizes) <= 50

    # §11 — all 120 rows became units, in file order.
    assert len(outcome.units) == ROW_COUNT
    assert [unit["location"]["row"] for unit in outcome.units] == list(
        range(1, ROW_COUNT + 1)
    )
    assert outcome.dataset["row_count"] == ROW_COUNT
    assert persisted == ROW_COUNT
