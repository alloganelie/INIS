"""§24.2/§27/§41.14 — the artifact row, its request link and its download.

The unit and API tests prove the delivery *announces* a file. This one proves the
chain survives PostgreSQL: the pipeline writes an ``artifacts`` row that carries
the ``request_id`` and ``created_at`` revision ``0013`` adds, the repository reads
it back from the migrated schema, and ``GET /v1/artifacts/{id}/download`` returns
exactly the bytes whose ``sha256`` the §24.2 record publishes.

Runs against the pgvector container (skipped when Docker is unavailable).
"""

from __future__ import annotations

import importlib
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.core.hashing import sha256_hex
from app.domain.value_objects.ulid import ULID
from app.main import app
from app.storage.database.engine import create_engine, set_default_engine
from app.storage.database.session import reset_session_maker
from app.storage.repositories.artifact_repository import ArtifactRepository

client = TestClient(app)


class MemoryStorage:
    """Object-store double backed by a dict, with the §4.3 client surface."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """Store the object and return its §24.2 ``storage_ref``."""
        self.objects[key] = data
        return f"s3://inis-artifacts/{key}"

    def download(self, key: str) -> bytes:
        """Return the stored bytes of *key*."""
        return self.objects[key]


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> MemoryStorage:
    """Install the in-memory object store on both sides of the delivery.

    The router module is fetched through :func:`importlib.import_module`: the
    package ``app.api.v1.artifacts`` re-exports ``router`` (the convention of
    every API package here), so the dotted path ``…artifacts.router`` resolves to
    the ``APIRouter`` object, not to the module that must be patched.
    """
    double = MemoryStorage()
    router_module = importlib.import_module("app.api.v1.artifacts.router")
    monkeypatch.setattr(
        "app.artifacts.delivery.delivery_service.build_object_storage", lambda: double
    )
    monkeypatch.setattr(router_module, "build_object_storage", lambda: double)
    return double


@pytest.fixture(autouse=True)
def _fresh_default_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rebuild the process-wide engine in the loop of the current test.

    ``get_default_engine`` caches one engine per URL, and an asyncpg engine is
    bound to the loop that created it: without this reset, a test running in the
    ``TestClient`` portal would reuse the engine of a previous pytest-asyncio
    loop and fail with "Event loop is closed". ``INIS_NULL_POOL`` keeps that
    engine from holding pooled connections when its loop is torn down.
    """
    monkeypatch.setenv("INIS_NULL_POOL", "1")
    set_default_engine(None)
    reset_session_maker()


async def _deliver_csv(db_url: str, storage: MemoryStorage) -> dict[str, Any]:
    """Run a real pipeline delivery of a CSV artifact against PostgreSQL."""
    runner = PipelineRunner()
    request_id = ULID.new("REQ_")
    return await runner.run(
        request_id,
        {"objective": "artifact persistence", "required_output": {"format": "csv"}},
    )


@pytest.mark.asyncio
async def test_pipeline_persists_the_artifact_with_its_request_link(
    db_url: str, monkeypatch: pytest.MonkeyPatch, storage: MemoryStorage
) -> None:
    """§24.2/§27 — the delivered file is a row of ``artifacts``."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    reset_session_maker()

    delivery = await _deliver_csv(db_url, storage)
    record = delivery["artifacts"][0]

    engine = create_engine(db_url)
    try:
        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT artifact_id, request_id, file_name, mime_type, sha256, "
                        "size_bytes, storage_ref, created_at FROM artifacts "
                        "WHERE artifact_id = :id"
                    ),
                    {"id": record["artifact_id"]},
                )
            ).mappings().first()

        assert row is not None, "the delivered artifact was not persisted"
        assert row["request_id"] == delivery["request_id"]
        assert row["file_name"] == record["file_name"]
        assert row["mime_type"] == "text/csv"
        assert row["sha256"] == record["sha256"]
        assert row["size_bytes"] == record["size_bytes"]
        assert row["storage_ref"] == record["storage_ref"]
        assert row["created_at"] is not None

        stored = await ArtifactRepository.get(engine, record["artifact_id"])
        listed = await ArtifactRepository.list_for_request(engine, delivery["request_id"])
    finally:
        await engine.dispose()

    assert stored is not None
    assert stored["artifact_id"] == record["artifact_id"]
    assert stored["request_id"] == delivery["request_id"]
    assert stored["source_ids"] == record["source_ids"]
    assert stored["provenance_complete"] is True
    assert [item["artifact_id"] for item in listed] == [record["artifact_id"]]


@pytest.mark.asyncio
async def test_artifact_download_returns_the_delivered_bytes(
    db_url: str, monkeypatch: pytest.MonkeyPatch, storage: MemoryStorage
) -> None:
    """§24.2/§32 — the bytes a client downloads are the bytes that were described."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    reset_session_maker()

    delivery = await _deliver_csv(db_url, storage)
    record = delivery["artifacts"][0]

    listing = client.get(f"/v1/artifacts?request_id={delivery['request_id']}")
    detail = client.get(f"/v1/artifacts/{record['artifact_id']}")
    download = client.get(f"/v1/artifacts/{record['artifact_id']}/download")

    assert listing.status_code == 200
    assert [item["artifact_id"] for item in listing.json()["artifacts"]] == [record["artifact_id"]]
    assert detail.status_code == 200
    assert detail.json()["sha256"] == record["sha256"]
    assert download.status_code == 200
    assert download.headers["content-type"].startswith("text/csv")
    assert record["file_name"] in download.headers["content-disposition"]
    assert sha256_hex(download.content) == record["sha256"]


@pytest.mark.asyncio
async def test_an_unknown_artifact_is_a_404(db_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """A request for a file that was never delivered must not invent one."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    reset_session_maker()
    assert client.get(f"/v1/artifacts/{ULID.new('REQ_')}").status_code == 404
