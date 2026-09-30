"""S3/MinIO client per §4.3 (object storage)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from app.core.errors import ValidationError
from app.core.size_limits import size_overflow_message

#: Bytes read per iteration when streaming an object to disk (1 MiB).
STREAM_CHUNK_SIZE = 1024 * 1024


class S3Client:
    """Client for S3/MinIO object storage.

    Supports both AWS S3 and MinIO (S3-compatible) for local development.
    """

    def __init__(
        self,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket_name: str,
        region: str = "us-east-1",
        secure: bool = True,
    ) -> None:
        """Initialize the S3/MinIO client.

        Args:
            endpoint_url: S3/MinIO endpoint URL (e.g., http://localhost:9000 for MinIO).
            access_key: Access key ID.
            secret_key: Secret access key.
            bucket_name: Default bucket name to use.
            region: AWS region (default: us-east-1).
            secure: Use HTTPS (default: True).
        """
        self._bucket_name = bucket_name
        self._s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
            config=Config(signature_version="s3v4"),
            use_ssl=secure,
        )

    def upload(
        self,
        key: str,
        data: bytes,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Upload data to S3/MinIO.

        Args:
            key: Object key (path in bucket).
            data: Binary data to upload.
            content_type: MIME type of the data.
            metadata: Optional metadata dictionary.

        Returns:
            The storage reference (s3://bucket/key).

        Raises:
            ClientError: If the upload fails.
        """
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type
        if metadata:
            extra_args["Metadata"] = metadata

        self._s3_client.put_object(
            Bucket=self._bucket_name,
            Key=key,
            Body=data,
            **extra_args,
        )
        return f"s3://{self._bucket_name}/{key}"

    def download(self, key: str) -> bytes:
        """Download data from S3/MinIO.

        Args:
            key: Object key to download.

        Returns:
            The binary data.

        Raises:
            ClientError: If the download fails.

        ⚠️ The whole object lands in memory. For anything that can be large, use
        :meth:`stream_to_file`, which refuses an oversized object **before** it is
        loaded (§41.13).
        """
        response = self._s3_client.get_object(Bucket=self._bucket_name, Key=key)
        return response["Body"].read()

    def head(self, key: str) -> dict:
        """Return the metadata of one object without reading it.

        Args:
            key: Object key to inspect.

        Returns:
            ``{"size_bytes": int | None, "content_type": str | None, "etag": str | None}``
            — the values the backend exposes, ``None`` when it exposes none.

        Raises:
            ClientError: If the object does not exist or the head fails.
        """
        response = self._s3_client.head_object(Bucket=self._bucket_name, Key=key)
        size = response.get("ContentLength")
        return {
            "size_bytes": int(size) if isinstance(size, int) else None,
            "content_type": response.get("ContentType") or None,
            "etag": response.get("ETag") or None,
        }

    def stream_to_file(
        self,
        key: str,
        path: str | Path,
        *,
        chunk_size: int = STREAM_CHUNK_SIZE,
        max_bytes: int | None = None,
        known_size: int | None = None,
    ) -> int:
        """Stream an object to *path*, chunk by chunk, refusing oversized ones.

        Unlike :meth:`download`, the object is never materialised in memory as a
        single blob: each chunk is written as it arrives, and the transfer is
        aborted as soon as ``max_bytes`` is exceeded — so refusing a 10 GiB object
        costs one chunk, not ten gigabytes of RAM (§41.13).

        Args:
            key: Object key to download.
            path: Destination file; its parent directory is created if needed.
            chunk_size: Bytes read per iteration.
            max_bytes: Ceiling for this transfer; ``None`` means unbounded.
            known_size: Size already learnt from :meth:`head`, to avoid a second
                HEAD request when the caller has it.

        Returns:
            The number of bytes written.

        Raises:
            ValidationError: When the object exceeds *max_bytes* (checked on the
                declared size first, then while streaming).
            ClientError: If the download fails.

        A refused or failed transfer leaves **no** partial file behind: a
        half-downloaded source must never be mistaken for a complete one (§0.2).
        """
        target = Path(path)
        if max_bytes is not None:
            declared = known_size
            if declared is None:
                declared = self.head(key)["size_bytes"]
            if declared is not None and declared > max_bytes:
                raise ValidationError(
                    size_overflow_message(
                        max_bytes, int(declared), action="Téléchargement refusé"
                    )
                )

        response = self._s3_client.get_object(Bucket=self._bucket_name, Key=key)
        body = response["Body"]
        target.parent.mkdir(parents=True, exist_ok=True)
        written = 0
        try:
            with target.open("wb") as handle:
                while True:
                    chunk = body.read(chunk_size)
                    if not chunk:
                        break
                    written += len(chunk)
                    if max_bytes is not None and written > max_bytes:
                        raise ValidationError(
                            size_overflow_message(
                                max_bytes, written, action="Téléchargement refusé"
                            )
                        )
                    handle.write(chunk)
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        finally:
            close = getattr(body, "close", None)
            if callable(close):
                close()
        return written

    def delete(self, key: str) -> bool:
        """Delete an object from S3/MinIO.

        Args:
            key: Object key to delete.

        Returns:
            True if deleted, False if not found.

        Raises:
            ClientError: If the delete fails for reasons other than not found.
        """
        try:
            self._s3_client.delete_object(Bucket=self._bucket_name, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                return False
            raise

    def exists(self, key: str) -> bool:
        """Check if an object exists in S3/MinIO.

        Args:
            key: Object key to check.

        Returns:
            True if the object exists, False otherwise.
        """
        try:
            self._s3_client.head_object(Bucket=self._bucket_name, Key=key)
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise

    def list(self, prefix: str = "", max_keys: int = 1000) -> list[str]:
        """List objects in the bucket with a given prefix.

        Args:
            prefix: Key prefix to filter objects.
            max_keys: Maximum number of keys to return.

        Returns:
            List of object keys.
        """
        response = self._s3_client.list_objects_v2(
            Bucket=self._bucket_name, Prefix=prefix, MaxKeys=max_keys
        )
        if "Contents" not in response:
            return []
        return [obj["Key"] for obj in response["Contents"]]

    def get_bucket_name(self) -> str:
        """Get the default bucket name."""
        return self._bucket_name
