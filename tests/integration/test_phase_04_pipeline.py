"""PHASE-04 pipeline smoke: Source -> Document coherence + CSV connector."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.domain.entities.document import Document
from app.domain.entities.source import Source
from app.domain.value_objects.ulid import ULID


def test_source_to_document() -> None:
    """A Document references its Source; both carry valid ULIDs."""
    source_id = ULID.new("SRC_")
    source = Source(
        source_id=source_id,
        type="file",
        url="file:///data/sample.csv",
        reliability_score=0.9,
        freshness={"observed_at": "2026-09-13"},
    )
    document = Document(
        document_id=ULID.new("DOC_"),
        source_id=source.source_id,
        mime_type="text/csv",
        content_hash="sha256:placeholder",
        storage_ref="objects/docs/placeholder",
    )

    assert document.source_id == source.source_id
    assert ULID.is_valid(source.source_id)
    assert ULID.is_valid(document.document_id)
    assert 0.0 <= source.reliability_score <= 1.0


async def test_csv_connector_smoke(tmp_path: Path) -> None:
    """CSVConnector discovers, retrieves and inspects a temp CSV file."""
    try:
        from app.connectors.files.csv_connector import CSVConnector
    except ImportError:
        pytest.skip("module absent: app.connectors.files.csv_connector")

    from app.connectors.base import Query, SourceCandidate

    csv_file = tmp_path / "sample.csv"
    csv_file.write_text("name,score\nalice,0.9\nbob,0.7", encoding="utf-8")

    connector = CSVConnector(base_path=str(tmp_path))
    candidates = await connector.discover(Query(query_string="sample"))
    assert len(candidates) == 1
    assert isinstance(candidates[0], SourceCandidate)

    raw = await connector.retrieve(candidates[0])
    assert raw.content_type == "text/csv"
    assert "alice" in str(raw.data)

    metadata = await connector.inspect(raw)
    assert metadata.record_count == 2
    assert set(metadata.schema or {}) == {"name", "score"}

    health = await connector.health_check()
    assert health.healthy
