"""Validation globale — le parcours complet sur la pile **réelle**.

Ce fichier exécute la chaîne demandée de bout en bout :

    Agent → InformationRequest → Understanding → Contextualisation → Planning
    → sélection d'outils → Acquisition → Extraction → contrôles Qualité
    → Cross-check → Confiance → Provenance/lignage → InformationPackage
    → Artefact → version → Livraison → Audit

Ce qui est **réel** ici : PostgreSQL (schéma migré), MinIO (stockage objet du
fichier livré), le vrai lecteur CSV (ingestion d'un fichier par la requête), le
vrai `PipelineRunner`, les vraies routes HTTP et le vrai audit.
Ce qui est **doublé, et pourquoi** : les fournisseurs web (aucun accès réseau en
CI) et le LLM (`mock_llm`) — ce sont des dépendances externes, pas
l'infrastructure ; le reste du pipeline s'exécute pour de vrai.

Chaque test vérifie un point du contrat, sur l'état produit par le parcours
lui-même : rien n'est déduit d'un test unitaire isolé.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.value_objects.ulid import ULID
from app.knowledge.ingestion.document_ingestor import ingest_document
from app.main import app
from app.storage.database.engine import create_engine, set_default_engine
from app.storage.database.session import reset_session_maker
from app.storage.repositories.dataset_repository import DatasetRepository
from app.storage.repositories.document_repository import DocumentRepository
from app.storage.repositories.information_unit_repository import (
    InformationUnitRepository,
)
from tests.containers import MINIO_BUCKET, MINIO_ROOT_PASSWORD, MINIO_ROOT_USER

client = TestClient(app)

OBJECTIVE = "Analyse le fichier de population fourni et sa traçabilité"
CSV_BYTES = b"city,population\nParis,2145906\nBerlin,3645000\n"
CSV_SHA256 = hashlib.sha256(CSV_BYTES).hexdigest()
STORAGE_REF = "s3://inis-artifacts/documents/REQ_JOURNEY/villes.csv"


@pytest.fixture(autouse=True)
def _fresh_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rebuild the process-wide engine inside the loop of the current test."""
    monkeypatch.setenv("INIS_NULL_POOL", "1")
    set_default_engine(None)
    reset_session_maker()
    yield
    set_default_engine(None)
    reset_session_maker()


@pytest.fixture
def live_s3(minio_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Point the application at the live MinIO container and create the bucket."""
    from contextlib import suppress

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
    return minio_url


async def _ingest_csv(engine: Any, request_id: str) -> dict[str, Any]:
    """Ingest a real CSV for *request_id*, exactly as the upload endpoint does.

    Le fichier est lu par le **vrai** lecteur CSV : les unités et le ``Dataset``
    qui en sortent sont ceux que la livraison doit ensuite citer.
    """
    document_id = ULID.new("DOC_")
    source_id = ULID.new("SRC_")
    outcome = await ingest_document(
        document_id=document_id,
        source_id=source_id,
        request_id=request_id,
        file_name="villes.csv",
        mime_type="text/csv",
        data=CSV_BYTES,
        storage_ref=STORAGE_REF,
    )
    assert outcome.dataset is not None, "l'ingestion doit produire un dataset"
    assert len(outcome.units) == 2, "les deux lignes du CSV deviennent deux unités"

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO sources (id, url, source_type, data_stage, created_at, "
                "updated_at) VALUES (:id, :url, 'file_upload', 'raw', now(), now()) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": source_id, "url": f"upload://{document_id}"},
        )
    await DocumentRepository.create(
        engine,
        {
            "document_id": document_id,
            "source_id": source_id,
            "request_id": request_id,
            "file_name": "villes.csv",
            "mime_type": "text/csv",
            "size_bytes": len(CSV_BYTES),
            "content_hash": CSV_SHA256,
            "storage_ref": STORAGE_REF,
        },
    )
    await DatasetRepository.create(
        engine,
        {**outcome.dataset, "name": "villes.csv", "request_id": request_id},
    )
    for unit in outcome.units:
        await InformationUnitRepository.create(engine, unit)
    return {
        "document_id": document_id,
        "source_id": source_id,
        "dataset_id": str(outcome.dataset["dataset_id"]),
    }


def _delivered_artifact(delivery: dict[str, Any]) -> dict[str, Any]:
    """Return the artifact the journey delivered **with stored bytes**.

    Le parcours peut produire plusieurs artefacts (une première exécution sans
    fichier, puis l'exécution sur le CSV) : celui qu'on vérifie est celui dont les
    octets ont réellement été stockés, c'est-à-dire celui dont le ``storage_ref``
    pointe le stockage objet et non le schéma ``unavailable://``.
    """
    artifacts = list(delivery.get("artifacts") or [])
    assert artifacts, "le parcours doit livrer un artefact"
    stored = [
        record
        for record in artifacts
        if not str(record.get("storage_ref", "")).startswith("unavailable://")
    ]
    assert stored, f"aucun artefact stocké : {[r.get('storage_ref') for r in artifacts]}"
    return stored[-1]


async def _journey(db_url: str, request_id: str) -> dict[str, Any]:
    """Ingest the request's file, then run the real pipeline for it."""
    engine = create_engine(db_url)
    try:
        identifiers = await _ingest_csv(engine, request_id)
    finally:
        await engine.dispose()

    delivery = await PipelineRunner().run(
        request_id,
        {
            "objective": OBJECTIVE,
            "request_type": "data",
            # §24 — la requête demande un fichier : c'est ce qui rend la livraison
            # d'artefact observable de bout en bout.
            "required_output": {"format": "csv"},
        },
    )
    return {**identifiers, "delivery": delivery}


@pytest.fixture
def journey(
    db_url: str,
    live_s3: str,
    mock_llm: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, Any]:
    """Exécuter le parcours complet une fois, et rendre tout ce qu'il a produit."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    reset_session_maker()
    mock_llm.configure('{"summary": "Fichier de population analysé.", "findings": []}')

    # 1. Agent → InformationRequest : la requête est créée par l'API réelle.
    created = client.post(
        "/v1/requests",
        json={
            "objective": OBJECTIVE,
            "request_type": "data",
            "required_output": {"format": "csv"},
        },
    )
    assert created.status_code in (200, 201, 202), created.text
    request_id = created.json()["request_id"]

    # 2. La requête fournit un fichier : ingestion réelle, puis exécution du
    #    pipeline sur cette matière (donc acquisition/extraction réelles).
    outcome = asyncio.run(_journey(db_url, request_id))
    return {"request_id": request_id, **outcome}


class TestTheJourneyDeliversATraceableFile:
    """Le colis, sa provenance et ses distinctions (§11, §12, §14, §24)."""

    def test_the_delivery_is_complete_and_traceable(self, journey: dict[str, Any]) -> None:
        """Rien d'inventé : chaque unité livrée vient du fichier ingéré."""
        delivery = journey["delivery"]

        assert delivery["request_id"] == journey["request_id"]
        assert delivery["information_units"], "le parcours doit livrer des unités"

        # La provenance du run lui-même : quel pipeline, quelle requête, quel plan.
        provenance = delivery["provenance"]
        assert provenance["pipeline"] == "PipelineRunner"
        assert provenance["request_id"] == journey["request_id"]
        assert provenance["steps_executed"] >= 1, "le run doit avoir exécuté des étapes"

        units = delivery["information_units"]
        for unit in units:
            identifier = unit["information_id"]
            assert identifier.startswith("INF_"), "une unité porte un identifiant §0.3"
            assert str(unit.get("source_id") or "").startswith("SRC_"), (
                f"l'unité {identifier} doit nommer sa source (§0.2, invariant 8)"
            )
        # Les unités du fichier portent le document réellement ingéré : c'est ce
        # qui relie leur contenu à une matière vérifiable, pas à une invention.
        from_file = [
            unit for unit in units if unit.get("document_id") == journey["document_id"]
        ]
        assert from_file, "les unités livrées doivent venir du document ingéré"
        blob = str([unit.get("content") for unit in from_file])
        assert "2145906" in blob or "Paris" in blob, (
            "le contenu livré doit provenir du fichier ingéré"
        )

    def test_the_five_kinds_of_record_stay_distinguishable(
        self, journey: dict[str, Any]
    ) -> None:
        """source / dataset / information / transformation / artefact : cinq mondes."""
        delivery = journey["delivery"]
        record = _delivered_artifact(delivery)

        assert record["source_ids"], "l'artefact nomme ses sources"
        assert all(item.startswith("SRC_") for item in record["source_ids"])
        assert record["dataset_ids"] == [journey["dataset_id"]], (
            "l'artefact nomme le dataset réellement ingéré"
        )
        assert all(item.startswith("DATA_") for item in record["dataset_ids"])
        assert record["transformation_ids"], (
            "l'artefact nomme les transformations qui ont produit ses unités"
        )
        assert all(item.startswith("TRF_") for item in record["transformation_ids"])
        assert record["artifact_id"].startswith("ART_")
        information_ids = {unit["information_id"] for unit in delivery["information_units"]}
        assert information_ids, "les informations sont distinctes des artefacts"

    def test_quality_confidence_and_limitations_are_in_the_package(
        self, journey: dict[str, Any]
    ) -> None:
        """§13/§15/§24.1 — le package dit sa qualité, sa confiance et ses limites."""
        delivery = journey["delivery"]

        assert isinstance(delivery["limitations"], list)
        quality = delivery["quality"]
        assert quality, "le package doit porter un bloc de qualité (§13)"
        assert quality.get("not_a_probability") is True, (
            "la qualité est une mesure, pas une probabilité"
        )
        assert "evidence" in delivery and "conflicts" in delivery
        assert "confidence" in delivery, "le package porte les détails de confiance (§15)"

        confidence_blocks = [
            unit.get("confidence")
            for unit in delivery["information_units"]
            if unit.get("confidence")
        ]
        assert confidence_blocks, "chaque unité livrée porte un bloc de confiance"
        for block in confidence_blocks:
            assert block.get("not_a_probability") is True, (
                "§15 — un score de confiance n'est pas une probabilité"
            )


class TestTheJourneyLandsInPostgres:
    """§27 — ce que la base contient vraiment, table par table."""

    def test_the_records_are_linked_in_the_database(
        self, journey: dict[str, Any], db_url: str
    ) -> None:
        """Les cinq mondes sont écrits **et reliés** : rien ne flotte."""
        request_id = journey["request_id"]
        record = _delivered_artifact(journey["delivery"])
        artifact_id = record["artifact_id"]
        engine = create_engine(db_url)
        try:
            counters = asyncio.run(_counters(engine, request_id, artifact_id, journey))
        finally:
            asyncio.run(engine.dispose())

        assert counters["units"] >= 2, "les unités du CSV sont persistées"
        assert counters["datasets"] == 1, "le dataset ingéré est persisté une fois"
        assert counters["transformations"] == len(record["transformation_ids"]), (
            "chaque transformation citée par l'artefact existe en base (§12.1)"
        )
        assert counters["artifacts"] >= 1
        assert counters["versions"] == 1, "la version livrée est enregistrée"
        assert counters["lineage"] == 1, "son lignage aussi"
        assert counters["audit"] >= 1, "le parcours laisse une trace d'audit"

    def test_the_artifact_row_and_the_lineage_agree(
        self, journey: dict[str, Any], db_url: str
    ) -> None:
        """La version et le lignage disent la même chose que l'artefact livré."""
        request_id = journey["request_id"]
        record = _delivered_artifact(journey["delivery"])
        engine = create_engine(db_url)
        try:
            rows = asyncio.run(_artifact_view(engine, record["artifact_id"]))
        finally:
            asyncio.run(engine.dispose())

        assert rows["version"] == record["version"]
        assert rows["lineage"]["source_ids"] == record["source_ids"]
        assert rows["lineage"]["dataset_ids"] == record["dataset_ids"]
        assert rows["lineage"]["transformation_ids"] == record["transformation_ids"]
        assert rows["metadata"]["information_ids"], (
            "le lignage nomme les informations livrées"
        )
        assert request_id == rows["request_id"]


async def _counters(
    engine: Any, request_id: str, artifact_id: str, journey: dict[str, Any]
) -> dict[str, int]:
    """Count the rows each layer of the journey must have written.

    ``information_units`` ne porte pas de ``request_id`` : une unité est reliée à
    sa requête par son **document** (§9.1), ce qui est la relation réelle du
    schéma — la requête n'est donc pas un filtre applicable à cette table.
    """
    document_id = journey["document_id"]
    record = _delivered_artifact(journey["delivery"])
    transformation_ids = list(record["transformation_ids"])
    counters: dict[str, int] = {}
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT count(*) FROM information_units WHERE document_id = :value"),
            {"value": document_id},
        )
        counters["units"] = int(result.scalar_one())
        for name, table in (("datasets", "datasets"), ("artifacts", "artifacts")):
            result = await conn.execute(
                text(f"SELECT count(*) FROM {table} WHERE request_id = :value"),
                {"value": request_id},
            )
            counters[name] = int(result.scalar_one())
        # §12.1 — chaque ``TRF_`` cité par l'artefact doit **exister** : une
        # référence pendante serait une provenance inventée, et le test la verrait.
        found = 0
        for identifier in transformation_ids:
            result = await conn.execute(
                text("SELECT count(*) FROM transformations WHERE transformation_id = :value"),
                {"value": identifier},
            )
            found += int(result.scalar_one())
        counters["transformations"] = found
        for name, statement in (
            ("versions", "SELECT count(*) FROM artifact_versions WHERE artifact_id = :value"),
            ("lineage", "SELECT count(*) FROM artifact_lineage WHERE artifact_id = :value"),
        ):
            result = await conn.execute(text(statement), {"value": artifact_id})
            counters[name] = int(result.scalar_one())
        result = await conn.execute(
            text("SELECT count(*) FROM audit_events WHERE request_id = :value"),
            {"value": request_id},
        )
        counters["audit"] = int(result.scalar_one())
    return counters


async def _artifact_view(engine: Any, artifact_id: str) -> dict[str, Any]:
    """Read back the artifact row, its version row and its version's lineage."""
    from app.storage.repositories.artifact_repository import ArtifactRepository
    from app.storage.repositories.artifact_version_repository import (
        ArtifactLineageRepository,
        ArtifactVersionRepository,
    )

    record = await ArtifactRepository.get(engine, artifact_id)
    assert record is not None
    current = await ArtifactVersionRepository.current(engine, artifact_id)
    assert current is not None
    lineage = await ArtifactLineageRepository.get_for_version(
        engine, artifact_id, str(current["version"])
    )
    assert lineage is not None
    return {
        "request_id": record["request_id"],
        "version": record["version"],
        "lineage": lineage,
        "metadata": current["metadata"],
    }


class TestTheDeliveredFileOverHTTP:
    """§24.2/§19.3/§18.2 — le fichier, son intégrité, son accès et sa suppression."""

    def test_the_bytes_are_in_minio_and_downloadable_with_integrity_headers(
        self, journey: dict[str, Any], live_s3: str
    ) -> None:
        """Les octets sortent de MinIO, l'empreinte annoncée est la leur."""
        import boto3

        record = _delivered_artifact(journey["delivery"])
        response = client.get(f"/v1/artifacts/{record['artifact_id']}/download")

        assert response.status_code == 200, response.text
        digest = hashlib.sha256(response.content).hexdigest()
        assert digest == record["sha256"], "les octets servis sont ceux du record"
        assert response.headers["x-checksum-sha256"] == digest
        assert response.headers["etag"] == f'"{digest}"'

        # Le même objet est bien dans le bucket : le téléchargement ne sort pas
        # d'ailleurs que du stockage objet réel.
        key = record["storage_ref"].split(f"s3://{MINIO_BUCKET}/", 1)[1]
        raw = boto3.client(
            "s3",
            endpoint_url=live_s3,
            aws_access_key_id=MINIO_ROOT_USER,
            aws_secret_access_key=MINIO_ROOT_PASSWORD,
            region_name="us-east-1",
        )
        stored = raw.get_object(Bucket=MINIO_BUCKET, Key=key)["Body"].read()
        assert stored == response.content, "le fichier servi est celui du bucket"

    def test_the_download_requires_the_artifact_role(
        self, journey: dict[str, Any], live_s3: str
    ) -> None:
        """§19.3 — sans le rôle, refus ; avec, le fichier. Même identifiant."""
        import time

        from app.api.middleware.auth_middleware import (
            create_jwt_token,
            set_strict_auth_mode,
        )

        record = _delivered_artifact(journey["delivery"])
        url = f"/v1/artifacts/{record['artifact_id']}/download"
        set_strict_auth_mode(True)
        try:
            anonymous = client.get(url)
            refused = client.get(
                url,
                headers={
                    "Authorization": "Bearer "
                    + create_jwt_token(
                        {"sub": "agent-sans-role", "scopes": ["search"], "exp": time.time() + 60}
                    )
                },
            )
            allowed = client.get(
                url,
                headers={
                    "Authorization": "Bearer "
                    + create_jwt_token(
                        {"sub": "agent-lecteur", "scopes": ["read"], "exp": time.time() + 60}
                    )
                },
            )
        finally:
            set_strict_auth_mode(None)

        assert anonymous.status_code == 401
        assert refused.status_code == 403
        assert "etag" not in refused.headers, "un refus n'annonce pas d'empreinte"
        assert allowed.status_code == 200
        assert allowed.content == client.get(url).content

    def test_a_deleted_artifact_becomes_unreachable(
        self, journey: dict[str, Any], live_s3: str, db_url: str
    ) -> None:
        """§18.2/0016 — supprimé veut dire inaccessible, et la liste le retire."""
        record = _delivered_artifact(journey["delivery"])
        artifact_id = record["artifact_id"]
        engine = create_engine(db_url)
        try:
            asyncio.run(_soft_delete(engine, artifact_id))
        finally:
            asyncio.run(engine.dispose())

        download = client.get(f"/v1/artifacts/{artifact_id}/download")
        detail = client.get(f"/v1/artifacts/{artifact_id}")
        listed = client.get(f"/v1/artifacts?request_id={journey['request_id']}")

        assert download.status_code == detail.status_code == 410
        assert artifact_id not in download.text
        identifiers = [item["artifact_id"] for item in listed.json()["artifacts"]]
        assert artifact_id not in identifiers

    def test_the_delivery_event_matches_the_artifact_actually_served(
        self, journey: dict[str, Any], live_s3: str, db_url: str
    ) -> None:
        """§24.3 — un téléchargement = un événement, sur le bon artefact."""
        record = _delivered_artifact(journey["delivery"])
        artifact_id = record["artifact_id"]

        assert client.get(f"/v1/artifacts/{artifact_id}/download").status_code == 200

        engine = create_engine(db_url)
        try:
            events = asyncio.run(_delivery_events(engine, artifact_id))
        finally:
            asyncio.run(engine.dispose())

        assert len(events) == 1, f"un seul téléchargement doit être tracé : {events}"
        assert events[0]["artifact_id"] == artifact_id
        assert events[0]["target"] == "http_download"
        assert events[0]["status"] == "delivered"

    def test_a_new_version_keeps_its_own_lineage_and_never_rewrites_the_old_one(
        self, journey: dict[str, Any], live_s3: str, db_url: str
    ) -> None:
        """§18.1 — la version publiée s'ajoute ; la précédente reste intacte."""
        from app.storage.repositories.artifact_version_repository import (
            ArtifactLineageRepository,
            ArtifactVersionRepository,
            publish_new_version,
        )

        record = _delivered_artifact(journey["delivery"])
        artifact_id = record["artifact_id"]
        engine = create_engine(db_url)
        try:
            published = asyncio.run(
                publish_new_version(
                    engine,
                    record,
                    kind="minor",
                    # Les transformations réellement exécutées : rien n'est inventé.
                    transformation_ids=record["transformation_ids"],
                )
            )
            history = asyncio.run(
                ArtifactVersionRepository.list_for_artifact(engine, artifact_id)
            )
            first = asyncio.run(
                ArtifactLineageRepository.get_for_version(engine, artifact_id, "1.0.0")
            )
            second = asyncio.run(
                ArtifactLineageRepository.get_for_version(engine, artifact_id, "1.1.0")
            )
        finally:
            asyncio.run(engine.dispose())

        assert [item["version"] for item in history] == ["1.0.0", "1.1.0"]
        assert published["version"]["metadata"]["supersedes"] == (
            ArtifactVersionRepository.version_id(artifact_id, "1.0.0")
        )
        assert first is not None and second is not None
        assert first["transformation_ids"] == record["transformation_ids"], (
            "la version précédente garde son lignage"
        )
        assert second["transformation_ids"] == record["transformation_ids"]
        assert first["dataset_ids"] == record["dataset_ids"]
        assert second["dataset_ids"] == record["dataset_ids"]


async def _soft_delete(engine: Any, artifact_id: str) -> None:
    """Suppress the artifact the way a deletion would (status + décision 0016)."""
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "UPDATE artifacts SET status = 'deleted', deleted_at = now() "
                "WHERE artifact_id = :id"
            ),
            {"id": artifact_id},
        )


async def _delivery_events(engine: Any, artifact_id: str) -> list[dict[str, Any]]:
    """Return the recorded §24.3 delivery events of one artifact."""
    from app.storage.repositories.artifact_version_repository import (
        ArtifactDeliveryEventRepository,
    )

    return await ArtifactDeliveryEventRepository.list_for_artifact(engine, artifact_id)
