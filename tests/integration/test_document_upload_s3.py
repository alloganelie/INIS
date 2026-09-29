"""§9.1/§18.1/§36.6 — an uploaded document is really stored, really persisted.

The API tests prove the contract with an in-memory store. This one runs the whole
chain against the live containers: the multipart upload reaches the API, the bytes
land in the S3-compatible bucket under a content-derived key, the ``sources`` and
``documents`` rows are written to PostgreSQL, the document is readable back, and
sending the same bytes again returns the *same* document.

Runs against the object-storage and pgvector containers (skipped without Docker).
"""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import suppress

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.storage.database.engine import create_engine, set_default_engine
from app.storage.database.session import reset_session_maker
from app.storage.object_storage.s3_client import S3Client
from tests.containers import MINIO_BUCKET, MINIO_ROOT_PASSWORD, MINIO_ROOT_USER

client = TestClient(app)

CSV_BYTES = b"city,population\nParis,2145906\nBerlin,3645000\n"
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n%%EOF\n"
PII_CSV = b"name,email\nAlice Dupont,alice@example.com\n"
OBJECTIVE = "Ingestion d'un fichier client"


@pytest.fixture(autouse=True)
def _fresh_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rebuild the process-wide engine in the loop of the current test."""
    monkeypatch.setenv("INIS_NULL_POOL", "1")
    set_default_engine(None)
    reset_session_maker()


@pytest.fixture
def live_storage(minio_url: str, monkeypatch: pytest.MonkeyPatch) -> S3Client:
    """Point the application at the live S3-compatible container."""
    import boto3

    raw = boto3.client(
        "s3",
        endpoint_url=minio_url,
        aws_access_key_id=MINIO_ROOT_USER,
        aws_secret_access_key=MINIO_ROOT_PASSWORD,
        region_name="us-east-1",
    )
    with suppress(raw.exceptions.BucketAlreadyOwnedByYou, raw.exceptions.BucketAlreadyExists):
        raw.create_bucket(Bucket=MINIO_BUCKET)

    monkeypatch.setenv("S3_ENDPOINT", minio_url)
    monkeypatch.setenv("S3_ACCESS_KEY", MINIO_ROOT_USER)
    monkeypatch.setenv("S3_SECRET_KEY", MINIO_ROOT_PASSWORD)
    monkeypatch.setenv("S3_BUCKET", MINIO_BUCKET)
    monkeypatch.setenv("S3_USE_SSL", "false")

    return S3Client(
        endpoint_url=minio_url,
        access_key=MINIO_ROOT_USER,
        secret_key=MINIO_ROOT_PASSWORD,
        bucket_name=MINIO_BUCKET,
        secure=False,
    )


def _create_request() -> str:
    """Create a request through the API and return its identifier."""
    created = client.post(
        "/v1/requests", json={"objective": OBJECTIVE, "request_type": "data"}
    )
    assert created.status_code == 201, created.text
    return created.json()["request_id"]


def _upload(request_id: str, content: bytes = CSV_BYTES, name: str = "villes.csv"):
    """Send one document to the upload endpoint."""
    return client.post(
        f"/v1/requests/{request_id}/documents",
        files={"file": (name, content, "text/csv")},
        data={"source_name": "Export client"},
    )


def _document_row(db_url: str, document_id: str) -> dict:
    """Read the persisted row through a dedicated engine."""
    engine = create_engine(db_url)
    try:

        async def read_row():
            async with engine.connect() as conn:
                return (
                    await conn.execute(
                        text(
                            "SELECT file_name, size_bytes, request_id, pii_classification "
                            "FROM documents WHERE id = :id"
                        ),
                        {"id": document_id},
                    )
                ).mappings().first()

        return dict(asyncio.run(read_row()) or {})
    finally:
        pass


def test_the_document_is_stored_in_s3_and_persisted_in_postgres(
    db_url: str, live_storage: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§18.1/§27 — the bytes are in the bucket, the row is in the table."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    request_id = _create_request()

    response = _upload(request_id)

    assert response.status_code == 201, response.text
    body = response.json()
    digest = hashlib.sha256(CSV_BYTES).hexdigest()
    assert body["sha256"] == digest
    assert not any("non persisté" in text_ for text_ in body["limitations"])

    key = body["storage_ref"].split(f"s3://{MINIO_BUCKET}/", 1)[1]
    assert key == f"documents/{request_id}/{digest}.csv"
    assert live_storage.download(key) == CSV_BYTES

    listing = client.get(f"/v1/documents?request_id={request_id}")
    assert listing.status_code == 200
    assert [item["document_id"] for item in listing.json()["documents"]] == [
        body["document_id"]
    ]
    detail = client.get(f"/v1/documents/{body['document_id']}")
    assert detail.status_code == 200
    assert detail.json()["sha256"] == digest


def test_the_source_row_exists_for_the_uploaded_document(
    db_url: str, live_storage: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§9/§27 — the document points at a real ``sources`` row, not a dangling id."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    request_id = _create_request()

    body = _upload(request_id).json()

    read_back = client.get(f"/v1/sources/{body['source_id']}")
    assert read_back.status_code == 200
    source = read_back.json()
    assert source["source_type"] == "file_upload"
    assert source["url"] == f"upload://{body['document_id']}"


def test_the_same_bytes_are_one_document(
    db_url: str, live_storage: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§18.1 — a retried upload returns the stored document, not a duplicate."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    request_id = _create_request()

    first = _upload(request_id).json()
    second = _upload(request_id).json()

    assert second["document_id"] == first["document_id"]
    assert second["idempotent"] is True
    assert any("déjà enregistrés" in text_ for text_ in second["limitations"])
    listing = client.get(f"/v1/documents?request_id={request_id}").json()
    assert listing["total"] == 1


def test_the_received_metadata_is_classified_and_persisted(
    db_url: str, live_storage: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§19.4 — what was received is classified; what is stored is redacted.

    The two halves are asserted together on purpose: sanitizing the name before
    classifying it would hide the very PII the classification exists to report,
    and storing the raw name would leak it into the object key.
    """
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    request_id = _create_request()

    body = _upload(request_id, content=PII_CSV, name="contacts_alice@example.com.csv").json()

    assert body["pii_classification"]["pii"] is True
    assert "@" not in body["file_name"]

    row = _document_row(db_url, body["document_id"])
    assert row["file_name"] == "contacts_alice_example.com.csv"
    assert row["size_bytes"] == len(PII_CSV)
    assert row["request_id"] == request_id
    assert row["pii_classification"]["pii"] is True
    assert "email" in row["pii_classification"]["categories"]


def test_an_unsupported_document_never_reaches_the_bucket(
    db_url: str, live_storage: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§25.2 — a refused type leaves no trace in storage nor in the database."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    request_id = _create_request()

    response = _upload(request_id, content=b"\x89PNG\r\n\x1a\nbinary", name="photo.png")

    assert response.status_code == 415
    assert client.get(f"/v1/documents?request_id={request_id}").json()["total"] == 0
    assert live_storage.list(prefix=f"documents/{request_id}/") == []


def test_a_pdf_is_accepted_as_a_pdf(
    db_url: str, live_storage: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§9.1 — the detected type decides the stored extension (§18.1)."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    request_id = _create_request()

    body = _upload(request_id, content=PDF_BYTES, name="rapport.csv").json()

    assert body["mime_type"] == "application/pdf"
    assert body["file_name"] == "rapport.pdf"
    assert body["storage_ref"].endswith(f"{hashlib.sha256(PDF_BYTES).hexdigest()}.pdf")
