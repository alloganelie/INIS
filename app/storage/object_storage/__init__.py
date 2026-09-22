"""Object storage module for S3/MinIO per §4.3."""

from app.storage.object_storage.s3_client import S3Client

__all__ = ["S3Client"]
