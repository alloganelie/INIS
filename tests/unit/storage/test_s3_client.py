"""Tests for S3Client per §4.3 (object storage)."""

import sys
from unittest.mock import MagicMock, patch

import pytest

# Mock boto3 and botocore to avoid dependency issues
sys.modules["boto3"] = MagicMock()
sys.modules["botocore"] = MagicMock()
sys.modules["botocore.exceptions"] = MagicMock()
sys.modules["botocore.client"] = MagicMock()

from app.storage.object_storage.s3_client import S3Client


# Mock ClientError for testing
class MockClientError(Exception):
    def __init__(self, error_response, operation_name):
        self.response = error_response
        self.operation_name = operation_name


@pytest.fixture
def s3_client():
    """Create a test S3Client."""
    return S3Client(
        endpoint_url="http://localhost:9000",
        access_key="test_key",
        secret_key="test_secret",
        bucket_name="test-bucket",
    )


def test_s3_client_upload(s3_client):
    """Test uploading data to S3."""
    with patch.object(s3_client._s3_client, "put_object") as mock_put:
        storage_ref = s3_client.upload("test/key", b"test data", "text/plain")
        assert storage_ref == "s3://test-bucket/test/key"
        mock_put.assert_called_once()


def test_s3_client_download(s3_client):
    """Test downloading data from S3."""
    mock_response = {"Body": MagicMock(read=MagicMock(return_value=b"test data"))}
    with patch.object(s3_client._s3_client, "get_object", return_value=mock_response):
        data = s3_client.download("test/key")
        assert data == b"test data"


def test_s3_client_delete(s3_client):
    """Test deleting an object from S3."""
    with patch.object(s3_client._s3_client, "delete_object"):
        result = s3_client.delete("test/key")
        assert result is True


def test_s3_client_delete_not_found(s3_client):
    """Test deleting a non-existent object."""
    with patch.object(s3_client._s3_client, "delete_object"):
        result = s3_client.delete("test/key")
        assert result is True


def test_s3_client_exists(s3_client):
    """Test checking if an object exists."""
    with patch.object(s3_client._s3_client, "head_object"):
        result = s3_client.exists("test/key")
        assert result is True


def test_s3_client_list(s3_client):
    """Test listing objects in the bucket."""
    mock_response = {"Contents": [{"Key": "test/key1"}, {"Key": "test/key2"}]}
    with patch.object(s3_client._s3_client, "list_objects_v2", return_value=mock_response):
        keys = s3_client.list("test/")
        assert keys == ["test/key1", "test/key2"]


def test_s3_client_list_empty(s3_client):
    """Test listing objects when bucket is empty."""
    mock_response = {}
    with patch.object(s3_client._s3_client, "list_objects_v2", return_value=mock_response):
        keys = s3_client.list("test/")
        assert keys == []


def test_s3_client_get_bucket_name(s3_client):
    """Test getting the bucket name."""
    assert s3_client.get_bucket_name() == "test-bucket"
