"""§5.2/§36.6 — une source **nommée** entre dans le colis comme un fichier téléversé.

Le lot L2.1 laissait une variante ouverte : un agent qui parle le protocole INIS
n'a pas de multipart à envoyer, il nomme un objet déjà présent dans le bucket du
déploiement. Ce test exerce ce chemin de bout en bout, contre le **vrai**
PostgreSQL et le **vrai** MinIO :

1. l'objet est déposé dans le bucket (comme un client l'aurait fait) ;
2. une requête est créée avec `source_ref` : l'objet est lu, typé par son contenu,
   ingéré (§11) et persisté avant que le run ne soit planifié ;
3. la matière relue et le colis §24.1 sont ceux d'un fichier fourni — mêmes unités
   localisées, même `Dataset`, même `storage_ref` que la référence nommée.

Conteneurs requis (pgvector + MinIO) : le test est ignoré sans Docker.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.knowledge.ingestion.object_intake import intake_source_ref
from app.knowledge.ingestion.request_material import load_request_material
from app.main import app
from app.storage.database.engine import set_default_engine
from app.storage.database.session import reset_session_maker
from app.storage.object_storage.s3_client import S3Client
from tests.containers import MINIO_BUCKET, MINIO_ROOT_PASSWORD, MINIO_ROOT_USER

client = TestClient(app)

CSV_BYTES = b"city,population\nParis,2145906\nBerlin,3645000\n"
OBJECTIVE = "Analyse le fichier déposé dans le bucket"
KEY = "documents/REQ_NAMED/villes.csv"


@pytest.fixture(autouse=True)
def _fresh_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rebuild the process-wide engine in the loop of the current test."""
    monkeypatch.setenv("INIS_NULL_POOL", "1")
    set_default_engine(None)
    reset_session_maker()
    yield
    set_default_engine(None)
    reset_session_maker()


@pytest.fixture
def live_storage(minio_url: str, monkeypatch: pytest.MonkeyPatch) -> S3Client:
    """Point the application at the live S3-compatible container §4.3."""
    import boto3

    raw = boto3.client(
        "s3",
        endpoint_url=minio_url,
        aws_access_key_id=MINIO_ROOT_USER,
        aws_secret_access_key=MINIO_ROOT_PASSWORD,
        region_name="us-east-1",
    )
    with suppress(raw.exceptions.BucketAlreadyOwnedByYou, raw.exceptions.BucketAlreadyExists):
        raw.create_bucket(Bucket=MINIO_BUCKET)

    monkeypatch.setenv("S3_ENDPOINT", minio_url)
    monkeypatch.setenv("S3_ACCESS_KEY", MINIO_ROOT_USER)
    monkeypatch.setenv("S3_SECRET_KEY", MINIO_ROOT_PASSWORD)
    monkeypatch.setenv("S3_BUCKET", MINIO_BUCKET)
    monkeypatch.setenv("S3_USE_SSL", "false")

    return S3Client(
        endpoint_url=minio_url,
        access_key=MINIO_ROOT_USER,
        secret_key=MINIO_ROOT_PASSWORD,
        bucket_name=MINIO_BUCKET,
        secure=False,
    )


def _source_ref() -> str:
    """Return the ``s3://`` reference of the object a client would have named."""
    return f"s3://{MINIO_BUCKET}/{KEY}"


def _named_request(payload_extra: dict[str, Any] | None = None):
    """Create a request through the API, naming its source instead of uploading it."""
    body: dict[str, Any] = {
        "objective": OBJECTIVE,
        "request_type": "data",
        "source_ref": _source_ref(),
    }
    body.update(payload_extra or {})
    return client.post("/v1/requests", json=body)


def test_the_named_object_is_ingested_and_consultable(
    db_url: str, live_storage: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§9.1/§11 — l'objet nommé devient un document, un dataset et des unités."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    live_storage.upload(KEY, CSV_BYTES, content_type="text/csv")

    created = _named_request()

    assert created.status_code == 201, created.text
    request_id = created.json()["request_id"]

    async def _read() -> Any:
        return await load_request_material(request_id)

    material = asyncio.run(_read())

    assert [document["mime_type"] for document in material.documents] == ["text/csv"]
    assert len(material.datasets) == 1
    assert material.datasets[0]["row_count"] == 2
    # The reference the client named *is* the location of what was read (§18.1).
    assert material.datasets[0]["storage_ref"] == _source_ref()
    assert len(material.units) == 2
    assert sorted(unit["location"]["row"] for unit in material.units) == [1, 2]
    assert all(
        unit["provenance"]["extracted_from"] == _source_ref() for unit in material.units
    )
    assert material.readers == ["read_csv"]
    assert material.limitations == []

    listing = client.get(f"/v1/documents?request_id={request_id}").json()
    assert listing["total"] == 1


def test_the_delivery_carries_the_named_source(
    db_url: str, live_storage: S3Client, mock_llm: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§24.1 — le colis d'une source nommée est celui d'un fichier fourni."""
    from unittest.mock import AsyncMock

    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    mock_llm.configure('{"summary": "Fichier nommé.", "findings": []}')
    search = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search", search
    )
    live_storage.upload(KEY, CSV_BYTES, content_type="text/csv")
    request_id = _named_request().json()["request_id"]

    delivery = asyncio.run(
        PipelineRunner().run(
            request_id, {"objective": OBJECTIVE, "request_type": "data"}
        )
    )

    # §7 — the request named its source: the web is not searched for it.
    assert search.await_count == 0
    assert len(delivery["datasets"]) == 1
    assert delivery["datasets"][0]["row_count"] == 2
    units = [unit for unit in delivery["information_units"] if unit.get("location")]
    assert sorted(unit["location"]["row"] for unit in units if unit["location"].get("row")) == [
        1,
        2,
    ]
    stages = [
        (item["parameters"]["stage"], item["tool"]) for item in delivery["transformations"]
    ]
    assert ("raw", "read_csv") in stages
    assert ("normalized", "DocumentIngestor.ingest") in stages


def test_a_named_source_outside_the_bucket_is_refused(
    db_url: str, live_storage: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§19.3 — le déploiement ne lit que le bucket qu'il possède."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)

    response = client.post(
        "/v1/requests",
        json={
            "objective": OBJECTIVE,
            "request_type": "data",
            "source_ref": "s3://someone-else/villes.csv",
        },
    )

    assert response.status_code == 422
    assert "bucket" in response.json()["detail"]


def test_the_intake_helper_reports_what_it_read_without_copying(
    db_url: str, live_storage: S3Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§5.2/§18.1 — la référence nommée reste la référence stockée."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    live_storage.upload(KEY, CSV_BYTES, content_type="text/csv")

    result = asyncio.run(
        intake_source_ref(request_id="REQ_NAMED_HELPER", source_ref=_source_ref())
    )

    assert result.summary.startswith("villes.csv (text/csv,")
    assert result.source_ref == _source_ref()
    assert len(result.units) == 2
    assert result.limitations == []

