"""Async object uploader with multipart support per §4.3 (object storage)."""

from typing import Optional

import aioboto3


class ObjectUploader:
    """Async uploader for S3/MinIO with multipart support for large files."""

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
        """Initialize the async uploader.

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

    async def upload(
        self,
        key: str,
        data: bytes,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Upload data to S3/MinIO with automatic multipart for large files.

        Args:
            key: Object key (path in bucket).
            data: Binary data to upload.
            content_type: MIME type of the data.
            metadata: Optional metadata dictionary.

        Returns:
            The storage reference (s3://bucket/key).
        """
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type
        if metadata:
            extra_args["Metadata"] = metadata

        async with self._session.client(
            "s3",
            endpoint_url=self._endpoint_url,
            use_ssl=self._secure,
        ) as s3:
            if len(data) < self.MULTIPART_THRESHOLD:
                # Single-part upload for small files
                await s3.put_object(
                    Bucket=self._bucket_name,
                    Key=key,
                    Body=data,
                    **extra_args,
                )
            else:
                # Multipart upload for large files
                await self._upload_multipart(s3, key, data, extra_args)

        return f"s3://{self._bucket_name}/{key}"

    async def _upload_multipart(
        self,
        s3,
        key: str,
        data: bytes,
        extra_args: dict,
    ) -> None:
        """Perform multipart upload for large files.

        Args:
            s3: Async S3 client.
            key: Object key.
            data: Binary data to upload.
            extra_args: Extra arguments for the upload.
        """
        # Initialize multipart upload
        response = await s3.create_multipart_upload(
            Bucket=self._bucket_name,
            Key=key,
            **extra_args,
        )
        upload_id = response["UploadId"]

        parts = []
        part_number = 1
        offset = 0

        try:
            # Upload parts
            while offset < len(data):
                chunk = data[offset : offset + self.MULTIPART_CHUNK_SIZE]
                part_response = await s3.upload_part(
                    Bucket=self._bucket_name,
                    Key=key,
                    PartNumber=part_number,
                    UploadId=upload_id,
                    Body=chunk,
                )
                parts.append(
                    {"PartNumber": part_number, "ETag": part_response["ETag"]}
                )
                offset += len(chunk)
                part_number += 1

            # Complete multipart upload
            await s3.complete_multipart_upload(
                Bucket=self._bucket_name,
                Key=key,
                UploadId=upload_id,
                MultipartUpload={"Parts": parts},
            )
        except Exception:
            # Abort on error
            await s3.abort_multipart_upload(
                Bucket=self._bucket_name,
                Key=key,
                UploadId=upload_id,
            )
            raise
