"""Shared testcontainers helpers for the INIS test suite per §33.2.

Until B4-bis this module was an empty placeholder while every integration
test re-declared its own ``postgres_container`` fixture — with slightly
different images, credentials and skip logic. The helpers below are the
single source of truth:

* :func:`docker_available` — cheap daemon probe used to skip cleanly when
  Docker is absent (local dev, some CI runners);
* :func:`postgres_container` / :func:`redis_container` — session-scoped
  fixtures starting the pinned images;
* :func:`postgres_url` / :func:`redis_url` — URL builders for the running
  containers;
* :func:`run_alembic_upgrade` — applies ``alembic upgrade head`` so every
  test sees the real §27 schema instead of a hand-made approximation.

Nothing here is imported by ``app/`` — this is a test-only module.
"""

from __future__ import annotations

import os
import subprocess
from typing import Any, Iterator

import pytest

#: Images are pinned so a test run is reproducible (§33.2).
POSTGRES_IMAGE = "pgvector/pgvector:pg16"
#: Dette n°1 — le serveur des tests est celui de la production (Valkey), pas un
#: Redis EOL : un test ne doit pas reproduire un backend qui n'existe plus.
#: Le client reste `redis.asyncio` : Valkey implémente le protocole Redis.
REDIS_IMAGE = "valkey/valkey:8-alpine"

#: Container-side ports (the host port is chosen by Docker).
POSTGRES_PORT = 5432
REDIS_PORT = 6379


def docker_available() -> bool:
    """Return ``True`` when a Docker daemon answers ``docker version``."""
    try:
        result = subprocess.run(
            ["docker", "version"],
            capture_output=True,
            timeout=10,
        )
    except Exception:
        return False
    return result.returncode == 0


def asyncpg_url(raw_url: str) -> str:
    """Force the asyncpg driver onto a testcontainers PostgreSQL URL.

    ``get_connection_url()`` defaults to ``psycopg2``, which is not an INIS
    dependency: the whole storage layer runs on ``asyncpg`` (§4.2).
    """
    return (
        raw_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        .replace("postgresql+psycopg://", "postgresql+asyncpg://")
        .replace("postgresql://", "postgresql+asyncpg://")
    )


def postgres_url(container: Any) -> str:
    """Return the asyncpg SQLAlchemy URL of a running ``PostgresContainer``."""
    return asyncpg_url(container.get_connection_url())


def redis_url(container: Any) -> str:
    """Return a ``redis://`` URL pointing at a running ``RedisContainer``."""
    host = container.get_container_host_ip()
    port = container.get_exposed_port(REDIS_PORT)
    return f"redis://{host}:{port}/0"


def run_alembic_upgrade(database_url: str) -> None:
    """Apply ``alembic upgrade head`` against *database_url* (§41.14).

    ``migrations/env.py`` reads ``DATABASE_URL``, so the URL is passed through
    the child environment instead of mutating ``os.environ`` of the caller.

    Raises:
        RuntimeError: If alembic fails, with its captured output attached so
            the migration error is visible in the pytest report.
    """
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    result = subprocess.run(
        ["python", "-m", "alembic", "upgrade", "head"],
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "alembic upgrade head failed:\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def _start_postgres() -> Any:
    """Start the pgvector container or return the raised exception."""
    try:
        from testcontainers.community.postgres import PostgresContainer

        container = PostgresContainer(
            POSTGRES_IMAGE,
            username="test",
            password="test",
            dbname="test",
            driver="asyncpg",
        )
        container.start()
    except Exception as exc:  # noqa: BLE001 - reported as a clean skip
        return exc
    return container


def _start_redis() -> Any:
    """Start the Redis container or return the raised exception."""
    try:
        from testcontainers.community.redis import RedisContainer

        container = RedisContainer(REDIS_IMAGE)
        container.start()
    except Exception as exc:  # noqa: BLE001 - reported as a clean skip
        return exc
    return container


@pytest.fixture(scope="session")
def postgres_container() -> Iterator[Any]:
    """Start a pgvector-enabled PostgreSQL container for the whole session."""
    if not docker_available():
        pytest.skip("Docker not available")
    started = _start_postgres()
    if isinstance(started, Exception):
        pytest.skip(f"Docker/testcontainers not available: {started}")
    try:
        yield started
    finally:
        started.stop()


#: Object storage image (S3-compatible: ``app.storage.object_storage`` talks to
#: it through boto3/aioboto3 with ``endpoint_url``). RustFS, not MinIO: the
#: previously pinned ``quay.io/minio/minio:RELEASE.2024-10-13T13-34-11Z`` was
#: withdrawn from Quay.io on 2026-09-24 and now answers "unauthorized", which
#: only passed locally thanks to the cached layer. RustFS speaks the same S3
#: API and implements ``/minio/health/live``, so no test change was needed.
MINIO_IMAGE = "rustfs/rustfs:1.0.0-rc.5"
MINIO_PORT = 9000
MINIO_ROOT_USER = "inis-test"
MINIO_ROOT_PASSWORD = "inis-test-secret"
MINIO_BUCKET = "inis-test-bucket"

#: Credential env vars — RustFS names them ``RUSTFS_*``, MinIO ``MINIO_*``.
_MINIO_CREDENTIAL_ENV = (
    ("RUSTFS_ACCESS_KEY", "RUSTFS_SECRET_KEY")
    if "rustfs" in MINIO_IMAGE
    else ("MINIO_ROOT_USER", "MINIO_ROOT_PASSWORD")
)


def minio_credentials_env() -> dict[str, str]:
    """Return the credential environment of the configured S3 backend."""
    user_var, password_var = _MINIO_CREDENTIAL_ENV
    return {user_var: MINIO_ROOT_USER, password_var: MINIO_ROOT_PASSWORD}


def _wait_for_http(endpoint: str, timeout: float = 60.0) -> None:
    """Block until *endpoint* serves a S3 request (any HTTP status but 000).

    A TCP connect alone is not enough: MinIO/RustFS bind the port before the
    routing table is ready, and the first boto3 call would then fail with a
    connection reset. Any HTTP answer — including ``403`` for an anonymous
    ``GET /`` — proves the API is up.

    Raises:
        TimeoutError: If no HTTP answer is received within *timeout* seconds.
    """
    import time
    import urllib.error
    import urllib.request

    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(endpoint, timeout=2)  # noqa: S310 - local http
            return
        except urllib.error.HTTPError:
            return  # 403/404 mean the S3 API answered
        except Exception as exc:  # noqa: BLE001 - retried until the deadline
            last_error = exc
        time.sleep(0.5)
    raise TimeoutError(f"object storage not ready at {endpoint}: {last_error}")


def _start_minio() -> Any:
    """Start the S3-compatible container or return the raised exception."""
    try:
        from testcontainers.core.container import DockerContainer

        container = DockerContainer(MINIO_IMAGE)
        for name, value in minio_credentials_env().items():
            container.with_env(name, value)
        container.with_exposed_ports(MINIO_PORT)
        if "rustfs" not in MINIO_IMAGE:
            # MinIO needs an explicit `server /data`; RustFS ships its own CMD.
            container.with_command("server /data")
        container.start()
        _wait_for_http(minio_endpoint(container))
    except Exception as exc:  # noqa: BLE001 - reported as a clean skip
        return exc
    return container


def minio_endpoint(container: Any) -> str:
    """Return the ``http://host:port`` endpoint of a running MinIO container."""
    host = container.get_container_host_ip()
    port = container.get_exposed_port(MINIO_PORT)
    return f"http://{host}:{port}"


@pytest.fixture(scope="session")
def minio_container() -> Iterator[Any]:
    """Start a MinIO container for the §4.3 object-storage tests."""
    if not docker_available():
        pytest.skip("Docker not available")
    started = _start_minio()
    if isinstance(started, Exception):
        pytest.skip(f"Docker/testcontainers/minio not available: {started}")
    try:
        yield started
    finally:
        started.stop()


@pytest.fixture(scope="session")
def redis_container() -> Iterator[Any]:
    """Start a Redis container for the §19/§41.5 shared-state tests."""
    if not docker_available():
        pytest.skip("Docker not available")
    started = _start_redis()
    if isinstance(started, Exception):
        pytest.skip(f"Docker/testcontainers/redis not available: {started}")
    try:
        yield started
    finally:
        started.stop()

