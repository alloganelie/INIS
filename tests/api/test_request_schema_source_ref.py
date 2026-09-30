"""§5.2/§9.1 — a client can name its source instead of uploading it.

``POST /v1/requests`` accepting ``source_ref: "s3://bucket/cle"`` is what closes
the L2.1 protocol variant: an agent that speaks INIS (§5.2) has no multipart to
send, and without this its only option would be to open a second channel. Three
things are pinned here:

* the schema accepts a complete ``s3://`` reference and **refuses** everything
  else (a local path is a read primitive over the host, §19);
* ``intake_source_ref`` really reads the object, types it **by its bytes** and
  turns it into §11 units — without copying it;
* an unreadable source is a refusal **naming the cause**, never a request created
  around material that does not exist (§25.2).

No Docker: the object store is a double that streams a temporary file exactly as
:class:`~app.storage.object_storage.s3_client.S3Client` does.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError as PydanticValidationError

from app.api.v1.requests.schemas import InformationRequestCreate
from app.core.errors import InfrastructureError, ValidationError
from app.knowledge.ingestion.object_intake import intake_source_ref
from app.main import app

client = TestClient(app)

CSV_BYTES = b"city,population\nParis,2145906\nBerlin,3645000\n"
BUCKET = "inis-artifacts"
CSV_REF = f"s3://{BUCKET}/documents/REQ_1/villes.csv"
OBJECTIVE = "Analyse le fichier déposé"


def _zip_bytes() -> bytes:
    """Return a ZIP payload: recognised by the sniffer, refused by §9.1."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("data/whatever.txt", "x")
    return buffer.getvalue()


class RecordingStorage:
    """Object-store double: one configured bucket, streamed to a real file."""

    def __init__(self, objects: dict[str, bytes], *, bucket: str = BUCKET) -> None:
        self.objects = objects
        self.bucket = bucket
        self.read_keys: list[str] = []

    def get_bucket_name(self) -> str:
        """Return the bucket this deployment is configured for (§19.3)."""
        return self.bucket

    def head(self, key: str) -> dict[str, Any]:
        """Return the object's declared size and content type."""
        if key not in self.objects:
            raise FileNotFoundError(key)
        payload = self.objects[key]
        return {"size_bytes": len(payload), "content_type": "application/octet-stream"}

    def stream_to_file(
        self,
        key: str,
        destination: Path,
        *,
        chunk_size: int = 1024,
        max_bytes: int | None = None,
        known_size: int | None = None,
    ) -> int:
        """Write the object to *destination*, refusing anything above the ceiling."""
        payload = self.objects[key]
        if max_bytes is not None and len(payload) > max_bytes:
            raise ValidationError(f"objet trop gros ({len(payload)} > {max_bytes} octets)")
        destination.write_bytes(payload)
        self.read_keys.append(key)
        return len(payload)


@pytest.fixture(autouse=True)
def _no_object_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    """No ``S3_*`` configuration unless a test installs the double."""
    for name in ("S3_ENDPOINT", "S3_ACCESS_KEY", "S3_SECRET_KEY", "S3_BUCKET"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _no_database(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run without PostgreSQL: what cannot be persisted is named, not hidden."""
    monkeypatch.delenv("INIS_DATABASE_URL", raising=False)


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> RecordingStorage:
    """Point the **real** downloader at an object store double.

    ``build_object_storage`` is patched in its own module, so the downloader's
    own logic still runs: reference parsing, bucket check (§19.3), size ceiling
    (§41.2) and the temporary file that is deleted afterwards.
    """
    import app.storage.object_storage.object_downloader as downloader

    double = RecordingStorage({"documents/REQ_1/villes.csv": CSV_BYTES})
    monkeypatch.setattr(downloader, "build_object_storage", lambda: double)
    return double


class TestSourceRefSchema:
    """§5.2 — the reference a client may name, and the ones it may not."""

    def test_a_complete_s3_reference_is_accepted(self) -> None:
        payload = InformationRequestCreate(objective="Analyse", source_ref=f" {CSV_REF} ")

        assert payload.source_ref == CSV_REF

    def test_no_reference_means_no_source(self) -> None:
        assert InformationRequestCreate(objective="Analyse").source_ref is None

    @pytest.mark.parametrize(
        "value",
        [
            "",
            "   ",
            "http://example.com/villes.csv",
            "file:///etc/passwd",
            "C:/Users/alice/villes.csv",
            f"s3://{BUCKET}",
            f"s3://{BUCKET}/",
            "s3:///villes.csv",
        ],
    )
    def test_every_other_reference_is_refused(self, value: str) -> None:
        with pytest.raises(PydanticValidationError):
            InformationRequestCreate(objective="Analyse", source_ref=value)


class TestIntakeSourceRef:
    """§9.1/§11 — the named object is read, typed by its bytes and turned into units."""

    async def test_the_object_is_ingested_without_being_copied(
        self, storage: RecordingStorage
    ) -> None:
        result = await intake_source_ref(request_id="REQ_TEST", source_ref=CSV_REF)

        assert result.file_name == "villes.csv"
        assert result.mime_type == "text/csv"
        assert result.size_bytes == len(CSV_BYTES)
        assert len(result.units) == 2
        assert [unit["location"]["row"] for unit in result.units] == [1, 2]
        # The client's reference *is* the storage reference: no second copy, and
        # the reader's temporary `file://` path never leaks into a unit (§18.1).
        assert result.source_ref == CSV_REF
        for unit in result.units:
            assert unit["provenance"]["extracted_from"] == CSV_REF
            assert "file://" not in json.dumps(unit)
        assert storage.read_keys == ["documents/REQ_1/villes.csv"]

    async def test_without_a_database_the_gap_is_named(
        self, storage: RecordingStorage
    ) -> None:
        result = await intake_source_ref(request_id="REQ_TEST", source_ref=CSV_REF)

        assert result.units, "les unités restent lues même sans base"
        assert any("non persisté" in text for text in result.limitations)

    async def test_an_unsupported_type_is_refused_by_name(self) -> None:
        from unittest.mock import patch

        import app.storage.object_storage.object_downloader as downloader

        double = RecordingStorage({"documents/REQ_1/archive.zip": _zip_bytes()})
        with (
            patch.object(downloader, "build_object_storage", lambda: double),
            pytest.raises(ValidationError, match="application/zip"),
        ):
            await intake_source_ref(
                request_id="REQ_TEST",
                source_ref=f"s3://{BUCKET}/documents/REQ_1/archive.zip",
            )

    async def test_another_bucket_is_refused(self, storage: RecordingStorage) -> None:
        """§19.3 — the reference names the deployment's bucket, or nothing."""
        with pytest.raises(ValidationError, match="bucket"):
            await intake_source_ref(
                request_id="REQ_TEST", source_ref="s3://someone-else/villes.csv"
            )
        assert storage.read_keys == []

    async def test_without_object_storage_the_source_cannot_be_read(self) -> None:
        with pytest.raises(InfrastructureError, match="Stockage objet non configuré"):
            await intake_source_ref(request_id="REQ_TEST", source_ref=CSV_REF)

    async def test_the_upload_ceiling_applies_to_a_named_source(
        self, storage: RecordingStorage
    ) -> None:
        """§41.2 — the same knob caps what comes in *and* what INIS fetches."""
        with pytest.raises(ValidationError, match="trop gros"):
            await intake_source_ref(
                request_id="REQ_TEST", source_ref=CSV_REF, budget={"max_storage_bytes": 8}
            )




class TestCreationRoute:
    """§5.2 — ``POST /v1/requests`` with a named source, and its refusals."""

    @pytest.fixture(autouse=True)
    def _hermetic_run(self, mock_llm: Any, monkeypatch: pytest.MonkeyPatch) -> None:
        """Keep the run triggered at creation from reaching the network (§28)."""
        from unittest.mock import AsyncMock

        mock_llm.configure('{"summary": "Fichier nommé.", "findings": []}')
        monkeypatch.setattr(
            "app.connectors.web.provider_router.ProviderRouter.search",
            AsyncMock(return_value=[]),
        )

    def test_a_named_source_is_read_before_the_run(
        self, storage: RecordingStorage, mock_llm: Any
    ) -> None:
        response = client.post(
            "/v1/requests",
            json={
                "objective": OBJECTIVE,
                "request_type": "data",
                "source_ref": CSV_REF,
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["request_id"].startswith("REQ_")
        assert storage.read_keys == ["documents/REQ_1/villes.csv"]

    def test_an_unreadable_named_source_refuses_the_request(
        self, storage: RecordingStorage, mock_llm: Any
    ) -> None:
        """§25.2 — no request is created around material that does not exist."""
        from unittest.mock import patch

        import app.storage.object_storage.object_downloader as downloader

        double = RecordingStorage({"documents/REQ_1/archive.zip": _zip_bytes()})
        with patch.object(downloader, "build_object_storage", lambda: double):
            response = client.post(
                "/v1/requests",
                json={
                    "objective": OBJECTIVE,
                    "request_type": "data",
                    "source_ref": f"s3://{BUCKET}/documents/REQ_1/archive.zip",
                },
            )

        assert response.status_code == 422
        assert "application/zip" in response.json()["detail"]

    def test_a_malformed_reference_is_refused_by_the_schema(self, mock_llm: Any) -> None:
        response = client.post(
            "/v1/requests",
            json={"objective": OBJECTIVE, "source_ref": "file:///etc/passwd"},
        )

        assert response.status_code == 422
        assert "source_ref" in response.text

    def test_without_a_reference_nothing_is_read(
        self, storage: RecordingStorage, mock_llm: Any
    ) -> None:
        """A request without ``source_ref`` behaves exactly as before (§5.2)."""
        response = client.post("/v1/requests", json={"objective": OBJECTIVE})

        assert response.status_code == 201
        assert storage.read_keys == []
