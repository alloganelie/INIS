"""S3/MinIO client per §4.3 (object storage)."""

from typing import Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError


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
        """
        response = self._s3_client.get_object(Bucket=self._bucket_name, Key=key)
        return response["Body"].read()

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
