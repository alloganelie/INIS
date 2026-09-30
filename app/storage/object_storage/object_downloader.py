"""Object downloaders per §4.3 (object storage).

Two download paths, and the difference between them is the whole point of this
module:

* :class:`ObjectDownloader` (async, ``aioboto3``, an **optional** dependency)
  returns the object as ``bytes`` — convenient, and unusable for a large source;
* :func:`download_object_to_temp` streams an object **to a temporary file**, in
  chunks, with the ``[limits].max_upload_bytes`` ceiling applied (the same knob as
  an upload, §41.2): a 10 GiB object is refused after one chunk instead of being
  loaded to be refused (§41.13). It is the path the file connectors take when they
  are pointed at an ``s3://bucket/key`` target (§9.1), and it uses the **synchronous**
  :class:`~app.storage.object_storage.s3_client.S3Client` — the client the
  application actually builds, ``aioboto3`` being optional and absent from most
  deployments.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.errors import InfrastructureError, ValidationError
from app.core.size_limits import effective_max_upload_bytes, size_overflow_message
from app.storage.object_storage.object_storage_factory import (
    build_object_storage,
    split_storage_ref,
)
from app.storage.object_storage.s3_client import STREAM_CHUNK_SIZE

__all__ = [
    "DownloadedObject",
    "ObjectDownloader",
    "download_limit",
    "download_object_to_temp",
    "download_overflow_message",
]


def _aioboto3() -> Any:
    """Return the optional ``aioboto3`` module or fail explicitly (§4.3)."""
    try:
        import aioboto3
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise InfrastructureError(
            "aioboto3 is required by the async object downloader (§4.3); "
            "install 'aioboto3' or use app.storage.object_storage.S3Client"
        ) from exc
    return aioboto3


def download_limit() -> int:
    """Return the byte ceiling of one download: ``[limits].max_upload_bytes``.

    The same ceiling as an upload, deliberately: INIS must not accept to
    *materialise* more bytes from a source than the deployment allows a client to
    send. ``[limits].max_upload_bytes`` (or ``INIS_MAX_UPLOAD_BYTES``) is the
    single knob for both directions (§41.2).
    """
    return effective_max_upload_bytes()


def download_overflow_message(limit: int, received: int | None = None) -> str:
    """Return the §25.2 message of a source refused for exceeding *limit*."""
    return size_overflow_message(limit, received, action="Source refusée")


@dataclass(frozen=True)
class DownloadedObject:
    """One object streamed to a temporary file, with what the backend declared."""

    uri: str
    path: Path
    bucket: str
    key: str
    size_bytes: int
    content_type: str | None


@contextmanager
def download_object_to_temp(
    uri: str,
    *,
    client: Any | None = None,
    limit: int | None = None,
    workdir: str | Path | None = None,
    chunk_size: int = STREAM_CHUNK_SIZE,
) -> Iterator[DownloadedObject]:
    """Stream the object *uri* into a temporary file and remove it afterwards.

    Args:
        uri: The ``s3://bucket/key`` reference of the source.
        client: The storage client to use; ``build_object_storage()`` when omitted.
        limit: Byte ceiling of this transfer; :func:`download_limit()` when omitted.
        workdir: Directory to create the temporary file in; the system temporary
            directory when omitted.
        chunk_size: Bytes read per iteration during the copy.

    Yields:
        The :class:`DownloadedObject` whose ``path`` holds the bytes. The file is
        deleted when the context exits — a caller that needs it longer must copy
        it first.

    Raises:
        ValidationError: When *uri* is not an ``s3://bucket/key`` reference, when
            its bucket is not the one this deployment is configured for (§19.3),
            or when the object exceeds the ceiling.
        InfrastructureError: When object storage is not configured at all.
    """
    reference = split_storage_ref(uri)
    if reference is None:
        raise ValidationError(
            f"Cible '{uri}' refusée : attendu une référence s3://bucket/chemin (§9.1)."
        )
    bucket, key = reference

    storage = client if client is not None else build_object_storage()
    if storage is None:
        raise InfrastructureError(
            "Stockage objet non configuré (S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY, "
            f"S3_BUCKET) : '{uri}' ne peut pas être lu (§25.2)."
        )

    configured = storage.get_bucket_name()
    if bucket != configured:
        raise ValidationError(
            f"Cible '{uri}' refusée : le stockage configuré ne donne accès qu'au "
            f"bucket '{configured}' (§19.3)."
        )
    if not key:
        raise ValidationError(f"Cible '{uri}' refusée : aucune clé d'objet (§9.1).")

    ceiling = limit if limit is not None else download_limit()
    header = storage.head(key)
    with tempfile.TemporaryDirectory(prefix="inis-download-", dir=workdir) as directory:
        destination = Path(directory) / (Path(key).name or "object")
        size = storage.stream_to_file(
            key,
            destination,
            chunk_size=chunk_size,
            max_bytes=ceiling,
            known_size=header.get("size_bytes"),
        )
        yield DownloadedObject(
            uri=f"s3://{bucket}/{key}",
            path=destination,
            bucket=bucket,
            key=key,
            size_bytes=size,
            content_type=header.get("content_type"),
        )


class ObjectDownloader:
    """Async downloader for S3/MinIO with multipart support for large files."""

    MULTIPART_THRESHOLD = 5 * 1024 * 1024  # 5 MB
    MULTIPART_CHUNK_SIZE = 8 * 1024 * 1024  # 8 MB

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket_name: str,
        region: str = "us-east-1",
        secure: bool = True,
    ) -> None:
        """Initialize the async downloader.

        Args:
            endpoint_url: S3/MinIO endpoint URL.
            access_key: Access key ID.
            secret_key: Secret access key.
            bucket_name: Default bucket name.
            region: AWS region (default: us-east-1).
            secure: Use HTTPS (default: True).
        """
        self._bucket_name = bucket_name
        self._session = _aioboto3().Session(
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        self._endpoint_url = endpoint_url
        self._secure = secure

    async def download(self, key: str) -> bytes:
        """Download data from S3/MinIO with automatic multipart for large files.

        Args:
            key: Object key to download.

        Returns:
            The binary data.
        """
        async with self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            use_ssl=self._secure,
        ) as s3:
            # Get object metadata to check size
            response = await s3.head_object(Bucket=self._bucket_name, Key=key)
            size = response["ContentLength"]

            if size < self.MULTIPART_THRESHOLD:
                # Single-part download for small files
                response = await s3.get_object(Bucket=self._bucket_name, Key=key)
                data = await response["Body"].read()
            else:
                # Multipart download for large files
                data = await self._download_multipart(s3, key, size)

        return data

    async def _download_multipart(
        self,
        s3,
        key: str,
        size: int,
    ) -> bytes:
        """Perform multipart download for large files.

        Args:
            s3: Async S3 client.
            key: Object key.
            size: Total size of the object.

        Returns:
            The concatenated binary data.
        """
        parts = []
        offset = 0
        part_number = 1

        while offset < size:
            end = min(offset + self.MULTIPART_CHUNK_SIZE, size)
            range_header = f"bytes={offset}-{end - 1}"

            response = await s3.get_object(
                Bucket=self._bucket_name,
                Key=key,
                Range=range_header,
            )
            part_data = await response["Body"].read()
            parts.append(part_data)

            offset = end
            part_number += 1

        return b"".join(parts)

    async def exists(self, key: str) -> bool:
        """Check if an object exists in S3/MinIO.

        Args:
            key: Object key to check.

        Returns:
            True if the object exists, False otherwise.
        """
        try:
            async with self._session.client(
                "s3",
                endpoint_url=self._endpoint_url,
                use_ssl=self._secure,
            ) as s3:
                await s3.head_object(Bucket=self._bucket_name, Key=key)
            return True
        except Exception:
            return False

    async def delete(self, key: str) -> bool:
        """Delete an object from S3/MinIO.

        Args:
            key: Object key to delete.

        Returns:
            True if deleted, False if not found.
        """
        try:
            async with self._session.client(
                "s3",
                endpoint_url=self._endpoint_url,
                use_ssl=self._secure,
            ) as s3:
                await s3.delete_object(Bucket=self._bucket_name, Key=key)
            return True
        except Exception:
            return False
