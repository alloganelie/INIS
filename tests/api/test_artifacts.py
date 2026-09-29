"""§24.2/§32 — the delivered file is announced, listed and fetched over HTTP.

Before this lot, ``artifacts`` was hard-coded to ``[]`` in the delivery and no
endpoint existed: a client that asked for a CSV received a promise and could not
list or download anything. These tests drive a real request through the API,
then read back exactly what §24.2 promises — and check that every degradation
(no object storage, no database) is *stated* rather than hidden behind an empty
200 or a silent 404.

Mocked providers only — no Docker, no network.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.domain.entities.artifact import Artifact
from app.domain.entities.search_result import SearchResult
from app.domain.value_objects.ulid import ULID
from app.main import app

client = TestClient(app)

OBJECTIVE = "Quelle est la capitale de la France ?"

#: §24.2 — the fields every delivered artifact record must expose.
ARTIFACT_FIELDS = set(Artifact.model_fields)


class RecordingStorage:
    """Object-store double: keeps the bytes and returns an ``s3://`` reference."""

    def __init__(self) -> None:
        self.uploads: list[tuple[str, bytes, str | None]] = []

    def upload(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """Store the object in memory and return its §24.2 ``storage_ref``."""
        self.uploads.append((key, data, content_type))
        return f"s3://inis-artifacts/{key}"


@pytest.fixture(autouse=True)
def _no_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run without PostgreSQL: the delivery falls back to the in-memory stores."""
    monkeypatch.delenv("INIS_DATABASE_URL", raising=False)


@pytest.fixture(autouse=True)
def _no_object_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run without ``S3_*`` configuration unless a test installs a double."""
    for name in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_BUCKET"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def web_doubles(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Serve one traceable source through the §9/§10 providers."""
    result = SearchResult(
        title="Paris — Wikipédia",
        url="https://fr.wikipedia.org/wiki/Paris",
        snippet="Paris est la capitale de la France.",
        score=0.95,
        provider="wikipedia",
    )
    search = AsyncMock(return_value=[result])
    extract = AsyncMock(
        return_value={
            "title": "Paris",
            "text": "Paris est la capitale de la France.",
            "language": "fr",
            "url": "https://fr.wikipedia.org/wiki/Paris",
            "error": None,
        }
    )
    monkeypatch.setattr("app.connectors.web.provider_router.ProviderRouter.search", search)
    monkeypatch.setattr(
        "app.connectors.web.extractors.wikipedia_extractor.WikipediaExtractor.extract",
        extract,
    )
    return {"search": search, "extract": extract}


def deliver(output_format: str | None = None) -> tuple[str, dict]:
    """Create a request through the API and return its delivered pipeline state."""
    body: dict = {"objective": OBJECTIVE, "request_type": "research"}
    if output_format is not None:
        body["required_output"] = {"format": output_format}
    created = client.post("/v1/requests", json=body)
    assert created.status_code == 201, created.text
    request_id = created.json()["request_id"]
    state = client.get(f"/v1/requests/{request_id}").json()["pipeline_state"]
    assert state is not None, "the §28 background run must have delivered something"
    return request_id, state


class TestDeliveredArtifacts:
    """§24.2 — a requested format produces a file, or an explicit statement."""

    def test_a_csv_request_announces_a_traceable_file(
        self, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        mock_llm.configure('{"summary": "Paris est la capitale.", "findings": []}')
        request_id, state = deliver("csv")

        artifacts = state["artifacts"]
        assert len(artifacts) == 1
        record = artifacts[0]
        assert set(record) == ARTIFACT_FIELDS | {"request_id", "created_at"}
        assert record["request_id"] == request_id
        assert record["artifact_type"] == "dataset_export"
        assert record["file_name"] == f"{request_id}.csv"
        assert record["mime_type"] == "text/csv"
        assert record["size_bytes"] > 0
        assert len(record["sha256"]) == 64
        assert record["source_ids"], "the exported file must name its sources (§0.2)"
        assert record["provenance_complete"] is True

    def test_the_default_request_attaches_no_file(
        self, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        """§7 — ``evidence_package`` is the response itself: nothing else is claimed."""
        mock_llm.configure('{"summary": "Paris est la capitale.", "findings": []}')
        _, state = deliver()

        assert state["artifacts"] == []
        assert not any("PDF" in limitation for limitation in state["limitations"])

    def test_a_pdf_request_stays_delivered_and_says_why(
        self, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        """§4.1/§25.2 — the refusal is explicit and does not break the delivery."""
        mock_llm.configure('{"summary": "Paris est la capitale.", "findings": []}')
        _, state = deliver("pdf")

        assert state["artifacts"] == []
        assert state["information_units"], "a refused format must not lose the delivery"
        assert any("PDF" in limitation for limitation in state["limitations"])

    def test_a_stored_artifact_announces_its_storage_reference(
        self, web_doubles: dict[str, AsyncMock], mock_llm, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With object storage, the record points at real bytes (§24.2)."""
        storage = RecordingStorage()
        monkeypatch.setattr(
            "app.artifacts.delivery.delivery_service.build_object_storage", lambda: storage
        )
        mock_llm.configure('{"summary": "Paris est la capitale.", "findings": []}')

        _, state = deliver("json")

        record = state["artifacts"][0]
        assert record["storage_ref"] == f"s3://inis-artifacts/{storage.uploads[0][0]}"
        assert not any("non stocké" in limitation for limitation in state["limitations"])


class TestArtifactEndpoints:
    """§32 — what the client can actually read back."""

    def test_artifacts_of_a_request_are_readable(
        self, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        mock_llm.configure('{"summary": "Paris est la capitale.", "findings": []}')
        request_id, state = deliver("xml")

        response = client.get(f"/v1/artifacts?request_id={request_id}")

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == len(body["artifacts"]) == 1
        assert body["artifacts"][0]["artifact_id"] == state["artifacts"][0]["artifact_id"]

    def test_an_unknown_request_is_a_404_not_an_empty_list(self) -> None:
        """A client must not read "no artifact" as "this request delivered none"."""
        response = client.get(f"/v1/artifacts?request_id={ULID.new('REQ_')}")

        assert response.status_code == 404

    def test_listing_everything_requires_persistence(self) -> None:
        """Without a database, an unfiltered list is refused, not faked empty."""
        response = client.get("/v1/artifacts")

        assert response.status_code == 503
        assert "not persisted" in response.json()["detail"]

    def test_detail_without_persistence_is_explicit(
        self, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        mock_llm.configure('{"summary": "Paris est la capitale.", "findings": []}')
        _, state = deliver("csv")
        artifact_id = state["artifacts"][0]["artifact_id"]

        response = client.get(f"/v1/artifacts/{artifact_id}")

        assert response.status_code == 503
        assert "not persisted" in response.json()["detail"]

    def test_download_of_an_unstored_artifact_is_explicit(
        self, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        """§24.2 — no silent 404 for a file that exists but was never stored."""
        mock_llm.configure('{"summary": "Paris est la capitale.", "findings": []}')
        _, state = deliver("csv")
        artifact_id = state["artifacts"][0]["artifact_id"]

        response = client.get(f"/v1/artifacts/{artifact_id}/download")

        assert response.status_code == 503
        assert "not persisted" in response.json()["detail"]
