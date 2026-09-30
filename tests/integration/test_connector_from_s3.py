"""§9.1/C3 — un connecteur lit vraiment un objet du stockage objet.

Le défaut C3 : un fichier qui n'est pas dans le répertoire de base était
invisible. Ce test exerce le chemin réel de bout en bout sur le conteneur S3
compatible (MinIO) : le fichier est déposé dans le bucket, le connecteur est
pointé sur ``s3://bucket/clé``, et la matière revient — sans que les octets
passent une seule fois entièrement par la mémoire.

Conteneur requis (MinIO/RustFS) : le test est ignoré sans Docker.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path

import pytest

from app.connectors.base import Query
from app.connectors.files.csv_connector import CONTENT_TYPE, CSVConnector
from app.core.errors import ValidationError
from app.storage.object_storage.s3_client import S3Client
from tests.containers import MINIO_BUCKET, MINIO_ROOT_PASSWORD, MINIO_ROOT_USER

CSV_BYTES = b"city,population\nParis,2145906\nBerlin,3645000\n"
KEY = "documents/REQ_L24/villes.csv"


@pytest.fixture
def storage(minio_url: str, monkeypatch: pytest.MonkeyPatch) -> S3Client:
    """Point the application at the live S3-compatible container (§4.3)."""
    import boto3

    raw = boto3.client(
        "s3",
        endpoint_url=minio_url,
        aws_access_key_id=MINIO_ROOT_USER,
        aws_secret_access_key=MINIO_ROOT_PASSWORD,
        region_name="us-east-1",
    )
    with suppress(
        raw.exceptions.BucketAlreadyOwnedByYou,
        raw.exceptions.BucketAlreadyExists,
    ):
        raw.create_bucket(Bucket=MINIO_BUCKET)

    monkeypatch.setenv("S3_ENDPOINT", minio_url)
    monkeypatch.setenv("S3_ACCESS_KEY", MINIO_ROOT_USER)
    monkeypatch.setenv("S3_SECRET_KEY", MINIO_ROOT_PASSWORD)
    monkeypatch.setenv("S3_BUCKET", MINIO_BUCKET)
    monkeypatch.setenv("S3_USE_SSL", "false")

    client = S3Client(
        endpoint_url=minio_url,
        access_key=MINIO_ROOT_USER,
        secret_key=MINIO_ROOT_PASSWORD,
        bucket_name=MINIO_BUCKET,
        secure=False,
    )
    client.upload(KEY, CSV_BYTES, content_type=CONTENT_TYPE)
    return client


def _uri() -> str:
    """Return the ``s3://`` reference of the uploaded object."""
    return f"s3://{MINIO_BUCKET}/{KEY}"


async def test_the_connector_reads_the_object_it_was_pointed_at(
    storage: S3Client, tmp_path: Path
) -> None:
    """§9.1 — cible explicite ``s3://`` : découverte, lecture, localisation."""
    connector = CSVConnector(base_path=str(tmp_path))

    candidates = await connector.discover(Query(filters={"location": _uri()}))

    assert len(candidates) == 1
    assert candidates[0].location == _uri()
    assert candidates[0].metadata["origin"] == "explicit_target"

    raw = await connector.retrieve(candidates[0])

    assert raw.data == CSV_BYTES.decode("utf-8")
    assert raw.content_type == CONTENT_TYPE
    assert raw.metadata["location"] == _uri()
    assert raw.metadata["storage_ref"] == _uri()
    assert raw.metadata["origin"] == "object_storage"
    assert raw.metadata["size_bytes"] == str(len(CSV_BYTES))


async def test_the_connector_inspects_what_it_downloaded(
    storage: S3Client, tmp_path: Path
) -> None:
    """§9.1 — le CSV distant est inspecté comme un CSV local (2 enregistrements)."""
    connector = CSVConnector(base_path=str(tmp_path))
    candidate = (await connector.discover(Query(filters={"location": _uri()})))[0]

    metadata = await connector.inspect(await connector.retrieve(candidate))

    assert metadata.record_count == 2
    assert metadata.schema == {"city": "string", "population": "string"}


async def test_an_object_over_the_ceiling_is_refused_without_downloading_it(
    storage: S3Client, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """§41.2/§41.13 — la borne est vérifiée avant le transfert, pas après."""
    monkeypatch.setenv("INIS_MAX_UPLOAD_BYTES", "10")
    connector = CSVConnector(base_path=str(tmp_path))
    candidate = (await connector.discover(Query(filters={"location": _uri()})))[0]
    before = storage.list(prefix="documents/REQ_L24/")

    with pytest.raises(ValidationError) as refusal:
        await connector.retrieve(candidate)

    assert "limite autorisée de 10 octets" in str(refusal.value)
    assert storage.list(prefix="documents/REQ_L24/") == before


async def test_a_wrong_object_suffix_is_refused_before_any_read(
    storage: S3Client, tmp_path: Path
) -> None:
    """§25.2 — l'objet existe, mais ce connecteur ne lit pas ce type : refus dit."""
    connector = CSVConnector(base_path=str(tmp_path))

    with pytest.raises(ValidationError) as refusal:
        await connector.discover(
            Query(filters={"location": f"s3://{MINIO_BUCKET}/documents/REQ_L24/x.xlsx"})
        )

    assert "ne lit que" in str(refusal.value)
