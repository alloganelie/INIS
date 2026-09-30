"""§4.3 — object storage against a real S3-compatible backend.

Documents and datasets are stored out of PostgreSQL, identified by a
``storage_ref`` and a content hash (§4.3, §18.1). These tests run ``S3Client``
against the live S3 container: the round trip, the reference format, the
metadata, and the fact that a missing key is reported rather than silently
returned as empty bytes.

Runs against the object-storage container (skip when Docker is unavailable).
"""

from __future__ import annotations

import hashlib
from contextlib import suppress
from typing import Any

import pytest

from app.storage.object_storage.s3_client import S3Client
from tests.containers import MINIO_BUCKET, MINIO_ROOT_PASSWORD, MINIO_ROOT_USER

PAYLOAD = b"city,population\nParis,2145906\nBerlin,3645000\n"
KEY = "tests/object-storage/cities.csv"
CONTENT_TYPE = "text/csv"


@pytest.fixture
def bucket(minio_url: str) -> str:
    """Create the session bucket if needed and return its name."""
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=minio_url,
        aws_access_key_id=MINIO_ROOT_USER,
        aws_secret_access_key=MINIO_ROOT_PASSWORD,
        region_name="us-east-1",
    )
    with suppress(
        client.exceptions.BucketAlreadyOwnedByYou, client.exceptions.BucketAlreadyExists
    ):
        client.create_bucket(Bucket=MINIO_BUCKET)
    return MINIO_BUCKET


@pytest.fixture
def storage(minio_url: str, bucket: str) -> S3Client:
    """Return an ``S3Client`` bound to the live container."""
    return S3Client(
        endpoint_url=minio_url,
        access_key=MINIO_ROOT_USER,
        secret_key=MINIO_ROOT_PASSWORD,
        bucket_name=bucket,
        secure=False,
    )


@pytest.fixture
def raw_client(minio_url: str) -> Any:
    """Return a boto3 client for metadata assertions."""
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=minio_url,
        aws_access_key_id=MINIO_ROOT_USER,
        aws_secret_access_key=MINIO_ROOT_PASSWORD,
        region_name="us-east-1",
    )


class TestStorageRoundTrip:
    """§4.3 — a stored object is retrievable and byte-identical."""

    def test_upload_returns_the_storage_reference(self, storage: S3Client) -> None:
        """The reference is ``s3://bucket/key``, the §24.2 ``storage_ref`` shape."""
        reference = storage.upload(KEY, PAYLOAD, content_type=CONTENT_TYPE)

        assert reference == f"s3://{MINIO_BUCKET}/{KEY}"

    def test_download_returns_the_stored_bytes(self, storage: S3Client) -> None:
        """What comes back is exactly what was stored (§18.1 identity)."""
        storage.upload(KEY, PAYLOAD, content_type=CONTENT_TYPE)

        stored = storage.download(KEY)

        assert stored == PAYLOAD
        assert hashlib.sha256(stored).hexdigest() == hashlib.sha256(PAYLOAD).hexdigest()

    def test_content_type_and_metadata_are_persisted(
        self, storage: S3Client, raw_client: Any
    ) -> None:
        """The declared MIME type and metadata survive the upload."""
        storage.upload(
            KEY, PAYLOAD, content_type=CONTENT_TYPE, metadata={"origin": "integration-test"}
        )

        head = raw_client.head_object(Bucket=MINIO_BUCKET, Key=KEY)
        assert head["ContentType"] == CONTENT_TYPE
        assert head["Metadata"]["origin"] == "integration-test"

    def test_exists_and_list_follow_the_bucket_state(
        self, storage: S3Client, bucket: str
    ) -> None:
        """``exists`` and ``list`` reflect what is actually stored."""
        missing_key = "tests/object-storage/missing.csv"
        storage.delete(KEY)

        assert storage.exists(missing_key) is False
        assert storage.exists(KEY) is False
        assert storage.get_bucket_name() == bucket

        storage.upload(KEY, PAYLOAD, content_type=CONTENT_TYPE)

        assert storage.exists(KEY) is True
        assert KEY in storage.list(prefix="tests/object-storage/")

    def test_delete_removes_the_object(self, storage: S3Client) -> None:
        """A deleted object is no longer reachable."""
        storage.upload(KEY, PAYLOAD, content_type=CONTENT_TYPE)

        assert storage.delete(KEY) is True
        assert storage.exists(KEY) is False

    def test_missing_object_is_reported_not_swallowed(self, storage: S3Client) -> None:
        """Downloading an absent key raises instead of returning empty bytes."""
        from botocore.exceptions import ClientError

        with pytest.raises(ClientError):
            storage.download("tests/object-storage/never-written.csv")

