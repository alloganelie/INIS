"""§9.1/§25.2/§36.6 — handing a file to INIS, and every way it can be refused.

``UploadFile`` had zero occurrence in ``app/`` before this lot: a client could
describe an objective, never provide a document. These tests drive the real
multipart endpoint and check both halves of the contract — what is accepted and
stored, and what is refused *with a reason a client can act on* (unsupported
type, oversized body, empty file, unknown request, no object storage).

Mocked providers only — no Docker, no network.
"""

from __future__ import annotations

import importlib
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.hashing import sha256_hex
from app.domain.entities.search_result import SearchResult
from app.domain.value_objects.ulid import ULID
from app.main import app

client = TestClient(app)

OBJECTIVE = "Compare la population des villes."
CSV_BYTES = b"city,population\nParis,2145906\nBerlin,3645000\n"
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class RecordingStorage:
    """Object-store double: keeps the bytes and returns an ``s3://`` reference."""

    def __init__(self) -> None:
        self.uploads: list[tuple[str, bytes, str | None]] = []

    def upload(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """Store the object in memory and return its storage reference."""
        self.uploads.append((key, data, content_type))
        return f"s3://inis-artifacts/{key}"


@pytest.fixture(autouse=True)
def _no_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run without PostgreSQL: the upload reports what it could not persist."""
    monkeypatch.delenv("INIS_DATABASE_URL", raising=False)


@pytest.fixture(autouse=True)
def _no_object_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run without ``S3_*`` configuration unless a test installs a double."""
    for name in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_BUCKET"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> RecordingStorage:
    """Install the in-memory object store on the upload router.

    The module is fetched through :func:`importlib.import_module`: the package
    ``app.api.v1.documents`` re-exports ``router`` (the convention of every API
    package here), so the dotted path ``…documents.router`` resolves to the
    ``APIRouter`` object rather than to the module to patch.
    """
    double = RecordingStorage()
    router_module = importlib.import_module("app.api.v1.documents.router")
    monkeypatch.setattr(router_module, "build_object_storage", lambda: double)
    return double


@pytest.fixture
def web_doubles(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Keep the background pipeline hermetic (§28 schedules it on creation)."""
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


def create_request(**extra: object) -> str:
    """Create a request through the API and return its identifier."""
    body: dict = {"objective": OBJECTIVE, "request_type": "data"}
    body.update(extra)
    created = client.post("/v1/requests", json=body)
    assert created.status_code == 201, created.text
    return created.json()["request_id"]


def upload(request_id: str, *, name: str, content: bytes, content_type: str = "text/csv"):
    """Send one document to the upload endpoint."""
    return client.post(
        f"/v1/requests/{request_id}/documents",
        files={"file": (name, content, content_type)},
        data={"source_name": "Export interne"},
    )


class TestAcceptedUpload:
    """§9.1 §18.1 — what the client receives, and where the bytes went."""

    def test_a_csv_is_accepted_and_described(
        self, storage: RecordingStorage, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        mock_llm.configure('{"summary": "Deux villes.", "findings": []}')
        request_id = create_request()

        response = upload(request_id, name="villes.csv", content=CSV_BYTES)

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["document_id"].startswith("DOC_")
        assert body["source_id"].startswith("SRC_")
        assert body["request_id"] == request_id
        assert body["file_name"] == "villes.csv"
        assert body["mime_type"] == "text/csv"
        assert body["size_bytes"] == len(CSV_BYTES)
        assert body["sha256"] == sha256_hex(CSV_BYTES)
        assert body["idempotent"] is False
        # §18.1 — the storage key is derived from the content hash.
        assert body["storage_ref"] == (
            f"s3://inis-artifacts/documents/{request_id}/{sha256_hex(CSV_BYTES)}.csv"
        )
        key, stored_bytes, content_type = storage.uploads[0]
        assert stored_bytes == CSV_BYTES
        assert content_type == "text/csv"
        assert key.endswith(f"{sha256_hex(CSV_BYTES)}.csv")

    def test_the_units_are_extracted_and_the_missing_persistence_is_stated(
        self, storage: RecordingStorage, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        """§11/§25.2 — the document yields units, and what is not persisted is named."""
        mock_llm.configure('{"summary": "Deux villes.", "findings": []}')
        request_id = create_request()

        body = upload(request_id, name="villes.csv", content=CSV_BYTES).json()

        units = body["information_units"]
        assert len(units) == 2
        assert {unit["type"] for unit in units} == {"record"}
        assert units[0]["location"]["kind"] == "row"
        assert units[0]["raw_reference"]["document_id"] == body["document_id"]
        assert any("non persisté" in text for text in body["limitations"])

    def test_the_detected_type_wins_over_the_file_name(
        self, storage: RecordingStorage, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        """A PDF named ``.csv`` is stored as a PDF (§9.1)."""
        mock_llm.configure('{"summary": "Deux villes.", "findings": []}')
        request_id = create_request()

        body = upload(
            request_id,
            name="rapport.csv",
            content=b"%PDF-1.7\n1 0 obj\nendobj\n%%EOF\n",
            content_type="text/csv",
        ).json()

        assert body["mime_type"] == "application/pdf"
        assert body["file_name"] == "rapport.pdf"

    def test_a_crafted_name_cannot_escape_the_storage_prefix(
        self, storage: RecordingStorage, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        mock_llm.configure('{"summary": "Deux villes.", "findings": []}')
        request_id = create_request()

        body = upload(request_id, name="../../etc/passwd.csv", content=CSV_BYTES).json()

        assert body["file_name"] == "passwd.csv"

    def test_the_pii_classification_of_the_name_is_returned(
        self, storage: RecordingStorage, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        """§19.4 — the received metadata is classified, and the result is visible."""
        mock_llm.configure('{"summary": "Deux villes.", "findings": []}')
        request_id = create_request()

        body = upload(
            request_id, name="contacts_alice@example.com.csv", content=CSV_BYTES
        ).json()

        assert body["pii_classification"]["pii"] is True
        assert "email" in body["pii_classification"]["categories"]
        assert body["pii_classification"]["sensitivity"] in {"medium", "high", "critical"}


class TestRefusedUpload:
    """§25.2 — every refusal names its cause and the way out."""

    def test_an_unknown_request_is_a_404(self, storage: RecordingStorage) -> None:
        response = upload(ULID.new("REQ_"), name="villes.csv", content=CSV_BYTES)

        assert response.status_code == 404

    def test_an_unsupported_type_names_the_detected_type(
        self, storage: RecordingStorage, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        mock_llm.configure('{"summary": "Deux villes.", "findings": []}')
        request_id = create_request()

        response = upload(
            request_id, name="photo.png", content=PNG_BYTES, content_type="image/png"
        )

        assert response.status_code == 415
        assert "image/png" in response.json()["detail"]
        assert storage.uploads == [], "a refused document must not be stored"

    def test_an_empty_file_is_refused(
        self, storage: RecordingStorage, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        mock_llm.configure('{"summary": "Deux villes.", "findings": []}')
        request_id = create_request()

        response = upload(request_id, name="vide.csv", content=b"")

        assert response.status_code == 422
        assert "vide" in response.json()["detail"].lower()

    def test_the_storage_budget_of_the_request_is_enforced(
        self, storage: RecordingStorage, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        """§41.2 — ``budget.max_storage_bytes`` is a ceiling, not a decoration."""
        mock_llm.configure('{"summary": "Deux villes.", "findings": []}')
        request_id = create_request(budget={"max_storage_bytes": 16})

        response = upload(request_id, name="villes.csv", content=CSV_BYTES)

        assert response.status_code == 413
        assert "16" in response.json()["detail"]
        assert storage.uploads == []

    def test_without_object_storage_the_upload_is_refused(
        self, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        """The binary *must* be stored: dropping it would make it unreadable."""
        mock_llm.configure('{"summary": "Deux villes.", "findings": []}')
        request_id = create_request()

        response = upload(request_id, name="villes.csv", content=CSV_BYTES)

        assert response.status_code == 503
        assert "Stockage objet" in response.json()["detail"]


class TestReadRoutes:
    """§32 — reading back what was accepted requires persistence, and says so."""

    def test_listing_without_a_database_is_explicit(self) -> None:
        response = client.get("/v1/documents")

        assert response.status_code == 503
        assert "non persistés" in response.json()["detail"]

    def test_detail_without_a_database_is_explicit(self) -> None:
        response = client.get(f"/v1/documents/{ULID.new('DOC_')}")

        assert response.status_code == 503
