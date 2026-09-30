"""§19.4 — the metadata of an uploaded document: what is classified, what is stored.

Two opposite mistakes are possible here, and this file pins both:

* classifying the *sanitized* name — sanitizing turns ``@`` into ``_``, so an
  email address in the file name would be erased **before** the classifier could
  report it (this bug was found by a test while implementing L2.1);
* storing the *raw* name — the storage key and the stored file name would then
  carry PII, and a crafted name could escape its prefix.

So: classification runs on what was received, storage uses a redacted name and a
key derived from the content hash.
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.v1.requests.router import _REQUESTS_STORE
from app.api.v1.requests.schemas import InformationRequestResponse
from app.connectors.files.mime_sniffer import sniff_mime_type
from app.core.hashing import sha256_hex
from app.main import app
from app.security.pii.sensitivity_classifier import SensitivityClassifier

client = TestClient(app)

CSV_BYTES = b"name,email\nAlice Dupont,alice@example.com\n"
PII_NAME = "contacts_alice@example.com.csv"


class RecordingStorage:
    """Object-store double that keeps the key it was asked to write."""

    def __init__(self) -> None:
        self.keys: list[str] = []

    def upload(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """Record the key and return a storage reference."""
        self.keys.append(key)
        return f"s3://inis-artifacts/{key}"


@pytest.fixture
def request_id(monkeypatch: pytest.MonkeyPatch) -> str:
    """Register a request in the in-memory store, without running a pipeline.

    The upload path only needs the request to exist (§32); going through
    ``POST /v1/requests`` would schedule a real §28 run and pull the web
    connectors into a security test that is about metadata handling.
    """
    identifier = "REQ_01M3Q0000000000000000SECUR"
    _REQUESTS_STORE[identifier] = InformationRequestResponse(
        request_id=identifier, objective="Test de sécurité", request_type="data"
    )
    monkeypatch.delenv("INIS_DATABASE_URL", raising=False)
    monkeypatch.delenv("S3_ENDPOINT", raising=False)
    yield identifier
    _REQUESTS_STORE.pop(identifier, None)


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> RecordingStorage:
    """Install the recording object store on the upload router."""
    double = RecordingStorage()
    router_module = importlib.import_module("app.api.v1.documents.router")
    monkeypatch.setattr(router_module, "build_object_storage", lambda: double)
    return double


class TestRedaction:
    """What is written must not carry what was received."""

    def test_the_stored_name_keeps_no_path_separator(self) -> None:
        sniffed = sniff_mime_type(CSV_BYTES)

        for crafted in ("../../etc/passwd.csv", r"C:\Windows\system32\cfg.csv"):
            stored = sniffed.safe_file_name(crafted, fallback_stem="DOC_1")
            assert "/" not in stored and "\\" not in stored
            assert stored in {"passwd.csv", "cfg.csv"}

    def test_the_stored_name_keeps_no_email_address(self) -> None:
        sniffed = sniff_mime_type(CSV_BYTES)

        stored = sniffed.safe_file_name(PII_NAME, fallback_stem="DOC_1")

        assert "@" not in stored
        assert "alice" not in stored or "_" in stored  # the address is broken apart

    def test_the_classification_does_see_the_email_of_the_received_name(self) -> None:
        """The property the endpoint relies on: classify *before* sanitizing."""
        classification = SensitivityClassifier().classify(PII_NAME)

        assert classification["pii"] is True
        assert "email" in classification["categories"]

    def test_the_sanitized_name_would_hide_the_email(self) -> None:
        """The reason the two steps are ordered this way."""
        sniffed = sniff_mime_type(CSV_BYTES)
        sanitized = sniffed.safe_file_name(PII_NAME, fallback_stem="DOC_1")

        assert SensitivityClassifier().classify(sanitized)["pii"] is False


class TestUploadMetadata:
    """End to end: the response reports the PII, the storage key reveals nothing."""

    def _upload(self, request_id: str, name: str = PII_NAME) -> Any:
        return client.post(
            f"/v1/requests/{request_id}/documents",
            files={"file": (name, CSV_BYTES, "text/csv")},
        )

    def test_the_key_is_the_content_hash_not_the_client_name(
        self, request_id: str, storage: RecordingStorage
    ) -> None:
        response = self._upload(request_id)

        assert response.status_code == 201, response.text
        key = storage.keys[0]
        assert key == f"documents/{request_id}/{sha256_hex(CSV_BYTES)}.csv"
        assert "@" not in key
        assert "alice" not in key
        assert "contacts" not in key

    def test_the_response_reports_the_pii_and_redacts_the_name(
        self, request_id: str, storage: RecordingStorage
    ) -> None:
        body = self._upload(request_id).json()

        assert body["pii_classification"]["pii"] is True
        assert "email" in body["pii_classification"]["categories"]
        assert body["pii_classification"]["sensitivity"] in {"medium", "high", "critical"}
        assert "@" not in body["file_name"]
        assert body["file_name"].endswith(".csv")

    def test_a_clean_name_reports_no_pii(self, request_id: str, storage: RecordingStorage) -> None:
        body = self._upload(request_id, name="villes.csv").json()

        assert body["pii_classification"]["pii"] is False
        assert body["file_name"] == "villes.csv"
