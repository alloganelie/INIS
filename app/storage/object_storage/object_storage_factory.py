"""Build the §4.3 object-storage client from the environment.

The delivery pipeline must be able to store the files it generated without the
callers hard-coding credentials: this module is the single place that reads the
``S3_*`` variables ``.env.example`` documents, and the single place that decides
what "object storage is configured" means.

``boto3`` is imported inside :func:`build_object_storage` on purpose: a process
that never delivers a file (unit tests, tooling) stays importable even without
the dependency, and the failure of a caller that does need it is explicit.
"""

from __future__ import annotations

import os
from typing import Any, Final

__all__ = [
    "REQUIRED_ENV_VARS",
    "build_object_storage",
    "missing_object_storage_env",
    "split_storage_ref",
    "storage_configured",
]

#: Variables that must all be set for object storage to be usable (§4.3).
REQUIRED_ENV_VARS: Final[tuple[str, ...]] = (
    "S3_ENDPOINT",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "S3_BUCKET",
)


def _truthy(value: str | None, *, default: bool) -> bool:
    """Return the boolean meaning of *value*, falling back to *default*."""
    if value is None or value == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def missing_object_storage_env() -> list[str]:
    """Return the ``S3_*`` variables that are not set (empty list when complete)."""
    return [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]


def split_storage_ref(storage_ref: str) -> tuple[str, str] | None:
    """Return ``(bucket, key)`` of an ``s3://bucket/key`` reference.

    §24.2 fixes the ``storage_ref`` as ``s3://bucket/chemin``. A reference that
    does not follow it (the ``unavailable://`` sentinel of an unstored file, for
    instance) returns ``None`` so the caller can refuse it explicitly instead of
    downloading the wrong object.
    """
    prefix = "s3://"
    reference = str(storage_ref or "")
    if not reference.startswith(prefix):
        return None
    bucket, separator, key = reference[len(prefix) :].partition("/")
    if not bucket or not separator or not key:
        return None
    return bucket, key


def storage_configured() -> bool:
    """Return whether the environment fully configures object storage (§4.3)."""
    return not missing_object_storage_env()


def build_object_storage() -> Any | None:
    """Return an :class:`~app.storage.object_storage.S3Client`, or ``None``.

    ``None`` does not mean "storage is broken": it means the deployment did not
    configure it, and callers must report that degradation (§25.2) instead of
    pretending the file was stored.

    Returns:
        The client bound to ``S3_BUCKET``, or ``None`` when one of
        :data:`REQUIRED_ENV_VARS` is missing.
    """
    if not storage_configured():
        return None

    from app.storage.object_storage.s3_client import S3Client

    return S3Client(
        endpoint_url=os.environ["S3_ENDPOINT"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
        bucket_name=os.environ["S3_BUCKET"],
        region=os.getenv("S3_REGION") or "us-east-1",
        # A local S3-compatible backend (docker-compose) has no TLS: the default
        # is therefore False and production sets S3_USE_SSL=true explicitly.
        secure=_truthy(os.getenv("S3_USE_SSL"), default=False),
    )
