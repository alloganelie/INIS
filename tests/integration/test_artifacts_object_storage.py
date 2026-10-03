"""§24.2/§24.3/§4.3 — the L1 exit criterion, proven against the live object store.

A request asking for ``xlsx`` must produce a workbook that is really uploaded to
the S3-compatible container, keep a ``storage_ref`` that points at it, and be
downloadable through the API handler with the very ``sha256`` the §24.2 record
publishes.

Nothing is monkeypatched on the storage path: the application builds its client
from the ``S3_*`` variables, exactly as a deployment does. The API handler is
awaited directly (rather than through ``TestClient``) so the database engine stays
in one event loop; the HTTP framing itself is covered by
``tests/integration/test_artifacts_persistence.py`` and ``tests/api/test_artifacts.py``.

Runs against the object-storage and pgvector containers (skipped without Docker).
"""

from __future__ import annotations

import hashlib
from contextlib import suppress

import pytest
from fastapi import Request

from app.api.v1.artifacts.router import download_artifact
from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.value_objects.ulid import ULID
from app.storage.database.engine import get_default_engine, set_default_engine
from app.storage.database.session import reset_session_maker
from app.storage.object_storage.s3_client import S3Client
from app.storage.repositories.artifact_repository import ArtifactRepository
from tests.containers import MINIO_BUCKET, MINIO_ROOT_PASSWORD, MINIO_ROOT_USER


def _anonymous_request() -> Request:
    """Return the request a caller without credentials produces (§19.3).

    The route is called directly here (the live object storage is the subject of
    the test), so the §19.3 guard needs the identity carrier the middleware fills
    over HTTP: an empty ``state`` is exactly an anonymous caller, which the policy
    allows on a public artifact and refuses on a `restricted` one.
    """
    return Request(scope={"type": "http", "headers": [], "method": "GET", "path": "/"})

#: §24.2 ``mime_type`` of an ``.xlsx`` delivery.
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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


@pytest.fixture(autouse=True)
def _fresh_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rebuild the process-wide engine in the loop of the current test."""
    monkeypatch.setenv("INIS_NULL_POOL", "1")
    set_default_engine(None)
    reset_session_maker()


@pytest.mark.asyncio
async def test_xlsx_artifact_is_stored_listed_and_downloadable(
    db_url: str, live_storage: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)

    request_id = ULID.new("REQ_")
    delivery = await PipelineRunner().run(
        request_id, {"objective": "export Excel", "required_output": {"format": "xlsx"}}
    )

    record = delivery["artifacts"][0]
    assert record["artifact_type"] == "dataset_export"
    assert record["mime_type"] == XLSX_MIME
    assert record["storage_ref"].startswith(f"s3://{MINIO_BUCKET}/deliveries/")
    assert not any("non stocké" in limitation for limitation in delivery["limitations"])

    # The object really exists, and its bytes are the ones the record describes.
    key = record["storage_ref"].split(f"s3://{MINIO_BUCKET}/", 1)[1]
    stored = live_storage.download(key)
    assert hashlib.sha256(stored).hexdigest() == record["sha256"]
    assert len(stored) == record["size_bytes"]

    # And the API serves exactly those bytes back.
    response = await download_artifact(record["artifact_id"], _anonymous_request())
    assert hashlib.sha256(response.body).hexdigest() == record["sha256"]
    assert response.headers["content-type"].startswith(XLSX_MIME)
    assert record["file_name"] in response.headers["content-disposition"]

    engine = get_default_engine()
    assert engine is not None
    listed = await ArtifactRepository.list_for_request(engine, request_id)
    assert [item["artifact_id"] for item in listed] == [record["artifact_id"]]
