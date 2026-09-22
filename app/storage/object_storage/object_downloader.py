"""Async object downloader with multipart support per §4.3 (object storage)."""

from typing import Optional

import aioboto3


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
        self._session = aioboto3.Session(
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
