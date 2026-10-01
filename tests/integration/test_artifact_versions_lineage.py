"""§24.2/§18.1/§24.3 — versions, lignage et livraisons d'un artefact, sur PostgreSQL.

Les tables ``artifact_versions``, ``artifact_lineage`` et
``artifact_delivery_events`` existaient depuis ``0005``/``0007`` et étaient
**vides** : un artefact livré n'avait qu'une version implicite, aucune histoire,
et rien ne reliait les octets à leurs sources, transformations et informations.

Ces tests exercent le **vrai** chemin (une livraison complète écrit sa version et
son lignage) et vérifient la chaîne demandée :

    source → transformation → information → artefact/version → téléchargement

La table ``artifacts`` reste la seule à porter ``deleted_at`` (décision ``0016``) :
l'historique est append-only, une suppression logique ne doit pas l'effacer.
"""

from __future__ import annotations

import hashlib
import importlib
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.value_objects.ulid import ULID
from app.main import app
from app.storage.database.engine import create_engine, set_default_engine
from app.storage.database.session import reset_session_maker
from app.storage.repositories.artifact_repository import ArtifactRepository
from app.storage.repositories.artifact_version_repository import (
    ArtifactLineageRepository,
    ArtifactVersionRepository,
    bump_version,
    publish_new_version,
    record_delivered_version,
    semver_key,
)

client = TestClient(app)

artifacts_router = importlib.import_module("app.api.v1.artifacts.router")

#: The three tables this lot fills, and the one column they must **not** carry.
APPEND_ONLY_TABLES = ("artifact_versions", "artifact_lineage", "artifact_delivery_events")

#: Les octets que le double de stockage sert, et l'empreinte qui les décrit : le
#: record inséré publie cette empreinte, comme une livraison réelle le fait.
ARTIFACT_BYTES = b"a,b\n1,2\n"
ARTIFACT_SHA256 = hashlib.sha256(ARTIFACT_BYTES).hexdigest()


class MemoryStorage:
    """Object-store double with both halves of the §4.3 client surface."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def upload(self, key: str, data: bytes, content_type: str | None = None) -> str:
        """Store the bytes and return the §24.2 ``storage_ref``."""
        self.objects[key] = data
        return f"s3://inis-artifacts/{key}"

    def download(self, key: str) -> bytes:
        """Return the bytes stored under *key*."""
        return self.objects[key]


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> MemoryStorage:
    """Install the double on both sides of the delivery."""
    double = MemoryStorage()
    monkeypatch.setattr(
        "app.artifacts.delivery.delivery_service.build_object_storage", lambda: double
    )
    monkeypatch.setattr(artifacts_router, "build_object_storage", lambda: double)
    return double


@pytest.fixture(autouse=True)
def _fresh_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bind the process (and the async engine) to the test database."""
    monkeypatch.setenv("INIS_NULL_POOL", "1")
    set_default_engine(None)
    reset_session_maker()


async def _deliver(db_url: str) -> dict[str, Any]:
    """Run a real delivery of a CSV artifact and return the whole colis."""
    return await PipelineRunner().run(
        ULID.new("REQ_"),
        {"objective": "lignage d'artefact", "required_output": {"format": "csv"}},
    )


@pytest.fixture
def artifact_like(db_url: str) -> dict[str, Any]:
    """Insert one artifact row (and its v1 + lineage): these tests are about history."""
    import asyncio

    record = {
        "artifact_id": f"ART_2026_8{ULID.new('DATA_')[-5:]}",
        "request_id": ULID.new("REQ_"),
        "artifact_type": "dataset",
        "file_name": "colis.csv",
        "mime_type": "text/csv",
        "version": "1.0.0",
        "size_bytes": len(ARTIFACT_BYTES),
        "sha256": ARTIFACT_SHA256,
        "storage_ref": "s3://inis-artifacts/colis.csv",
        "purpose": "livraison",
        "source_ids": ["SRC_01M3T0000000000000000000001"],
        "dataset_ids": [],
        "transformation_ids": ["TRF_01M3T0000000000000000000001"],
        "quality_score": 0.9,
        "confidence_score": 0.8,
        "provenance_complete": True,
        "status": "available",
    }

    async def insert() -> None:
        engine = create_engine(db_url)
        try:
            await ArtifactRepository.create(engine, record)
            await record_delivered_version(
                engine,
                record,
                information_ids=["INF_01M3T0000000000000000000001"],
            )
        finally:
            await engine.dispose()

    asyncio.run(insert())
    return record


class TestSemver:
    """Les versions restent des versions (§24.2), même hors base."""

    def test_versions_are_compared_numerically(self) -> None:
        assert semver_key("1.10.0") > semver_key("1.9.0"), (
            "comparer les versions comme du texte classerait 1.10.0 avant 1.9.0"
        )

    def test_a_malformed_version_sorts_last_instead_of_raising(self) -> None:
        assert semver_key("pas-une-version") > semver_key("99.99.99")

    def test_bump_follows_the_kind_of_change(self) -> None:
        assert bump_version("1.4.2", "patch") == "1.4.3"
        assert bump_version("1.4.2", "minor") == "1.5.0"
        assert bump_version("1.4.2", "major") == "2.0.0"

    def test_an_unknown_bump_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown version bump"):
            bump_version("1.0.0", "immense")

    def test_a_malformed_version_cannot_be_bumped(self) -> None:
        with pytest.raises(ValueError, match="not a semantic version"):
            bump_version("1.0", "patch")


class TestTheDeliveryWritesTheFirstVersion:
    """Une livraison réelle écrit la version v1 et son lignage."""

    @pytest.mark.asyncio
    async def test_the_delivered_file_has_a_version_row_and_a_lineage_row(
        self, db_url: str, monkeypatch: pytest.MonkeyPatch, storage: MemoryStorage
    ) -> None:
        monkeypatch.setenv("INIS_DATABASE_URL", db_url)
        reset_session_maker()

        delivery = await PipelineRunner().run(
            ULID.new("REQ_"),
            {"objective": "version et lignage", "required_output": {"format": "csv"}},
        )
        record = delivery["artifacts"][0]
        artifact_id = record["artifact_id"]

        engine = create_engine(db_url)
        try:
            history = await ArtifactVersionRepository.list_for_artifact(engine, artifact_id)
            current = await ArtifactVersionRepository.current(engine, artifact_id)
            lineage = await ArtifactLineageRepository.get_for_version(
                engine, artifact_id, str(record["version"])
            )
        finally:
            await engine.dispose()

        assert history, "la livraison doit enregistrer la version livrée"
        assert current is not None
        assert current["version"] == record["version"] == "1.0.0"
        assert current["metadata"]["sha256"] == record["sha256"]
        assert current["metadata"]["storage_ref"] == record["storage_ref"]
        assert current["metadata"]["request_id"] == delivery["request_id"]
        # Le maillon « information » : les unités livrées, pas une liste inventée.
        assert current["metadata"]["information_ids"] == [
            unit["information_id"] for unit in delivery["information_units"]
        ]
        assert lineage is not None, "le lignage de la version livrée doit être écrit"
        assert lineage["source_ids"] == list(record["source_ids"])
        assert lineage["artifact_lineage_id"] == ArtifactLineageRepository.lineage_id(
            artifact_id, str(record["version"])
        )

    @pytest.mark.asyncio
    async def test_the_chain_from_source_to_artifact_is_readable(
        self, db_url: str, monkeypatch: pytest.MonkeyPatch, storage: MemoryStorage
    ) -> None:
        """``source → information → artefact`` est lisible dans les deux tables."""
        monkeypatch.setenv("INIS_DATABASE_URL", db_url)
        reset_session_maker()

        delivery = await PipelineRunner().run(
            ULID.new("REQ_"),
            {"objective": "chaîne de provenance", "required_output": {"format": "json"}},
        )
        record = delivery["artifacts"][0]

        engine = create_engine(db_url)
        try:
            version = await ArtifactVersionRepository.current(engine, record["artifact_id"])
            lineage = await ArtifactLineageRepository.get_for_version(
                engine, record["artifact_id"], str(record["version"])
            )
        finally:
            await engine.dispose()

        assert version is not None and lineage is not None
        sources_of_units = {
            unit["source_id"]
            for unit in delivery["information_units"]
            if unit.get("source_id")
        }
        assert set(lineage["source_ids"]) == sources_of_units, (
            "les sources du lignage sont celles des unités livrées"
        )
        information_ids = set(version["metadata"]["information_ids"])
        assert information_ids == {
            unit["information_id"] for unit in delivery["information_units"]
        }


class TestANewVersionKeepsTheHistoryCoherent:
    """Une nouvelle version s'ajoute, elle ne réécrit rien."""

    @pytest.mark.asyncio
    async def test_the_history_grows_and_names_the_current_version(
        self, db_url: str, artifact_like: dict[str, Any]
    ) -> None:
        """Version courante, versions précédentes, et ce que chacune a produit."""
        artifact = artifact_like
        engine = create_engine(db_url)
        try:
            published = await publish_new_version(
                engine,
                artifact,
                kind="minor",
                transformation_ids=["TRF_01M3T0000000000000000000002"],
                information_ids=["INF_01M3T0000000000000000000002"],
            )
            history = await ArtifactVersionRepository.list_for_artifact(
                engine, artifact["artifact_id"]
            )
            current = await ArtifactVersionRepository.current(engine, artifact["artifact_id"])
            artifact_row = await ArtifactRepository.get(engine, artifact["artifact_id"])
            self_lineage = await ArtifactLineageRepository.list_for_artifact(
                engine, artifact["artifact_id"]
            )
        finally:
            await engine.dispose()

        assert [row["version"] for row in history] == ["1.0.0", "1.1.0"]
        assert current is not None and current["version"] == "1.1.0"
        assert artifact_row is not None and artifact_row["version"] == "1.1.0", (
            "la version livrée est lisible depuis l'artefact lui-même"
        )
        assert published["version"]["metadata"]["supersedes"] == (
            ArtifactVersionRepository.version_id(artifact["artifact_id"], "1.0.0")
        )
        assert current["metadata"]["transformation_ids"] == [
            "TRF_01M3T0000000000000000000002"
        ], "chaque version nomme la transformation qui l'a produite"
        assert [row["transformation_ids"] for row in self_lineage] == [
            ["TRF_01M3T0000000000000000000001"],
            ["TRF_01M3T0000000000000000000002"],
        ], "le lignage de chaque version reste distinct et cohérent"

    @pytest.mark.asyncio
    async def test_reappending_a_version_never_rewrites_it(
        self, db_url: str, artifact_like: dict[str, Any]
    ) -> None:
        """Une version publiée est immuable (§18.1), même rejouée."""
        artifact = artifact_like
        engine = create_engine(db_url)
        try:
            await ArtifactVersionRepository.append(
                engine,
                artifact["artifact_id"],
                "1.0.0",
                {"sha256": "réécriture-interdite"},
            )
            stored = await ArtifactVersionRepository.get(
                engine,
                ArtifactVersionRepository.version_id(artifact["artifact_id"], "1.0.0"),
            )
        finally:
            await engine.dispose()

        assert stored is not None
        assert stored["metadata"]["sha256"] != "réécriture-interdite", (
            "un second enregistrement ne doit pas modifier la version publiée"
        )
        assert stored["metadata"]["sha256"] == artifact["sha256"]


class TestALogicalDeletionKeepsTheHistory:
    """Décision ``0016`` : ces tables sont l'historique, elles ne se suppriment pas."""

    @pytest.mark.asyncio
    async def test_the_append_only_tables_have_no_deleted_at(self, db_url: str) -> None:
        """Aucune des trois tables ne reçoit ``deleted_at`` (contrairement à `artifacts`)."""
        engine = create_engine(db_url)
        try:
            columns = {
                table: await self._columns(engine, table) for table in APPEND_ONLY_TABLES
            }
            artifact_columns = await self._columns(engine, "artifacts")
        finally:
            await engine.dispose()

        for table, names in columns.items():
            assert "deleted_at" not in names, (
                f"{table} est append-only : la décision 0016 ne lui donne pas "
                "de suppression logique"
            )
        assert "deleted_at" in artifact_columns, "l'artefact, lui, se supprime logiquement"

    @pytest.mark.asyncio
    async def test_a_soft_deleted_artifact_keeps_its_versions_and_lineage(
        self, db_url: str, artifact_like: dict[str, Any]
    ) -> None:
        """Une suppression logique ne casse pas l'historique."""
        engine = create_engine(db_url)
        try:
            async with engine.begin() as conn:
                await conn.execute(
                    text(
                        "UPDATE artifacts SET status = 'deleted', deleted_at = now() "
                        "WHERE artifact_id = :id"
                    ),
                    {"id": artifact_like["artifact_id"]},
                )
            history = await ArtifactVersionRepository.list_for_artifact(
                engine, artifact_like["artifact_id"]
            )
            lineage = await ArtifactLineageRepository.list_for_artifact(
                engine, artifact_like["artifact_id"]
            )
        finally:
            await engine.dispose()

        assert [row["version"] for row in history] == ["1.0.0"]
        assert lineage, "le lignage survit à la suppression logique de l'artefact"

    @staticmethod
    async def _columns(engine: Any, table: str) -> set[str]:
        """Return the column names of *table* from the migrated schema."""
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :table"
                ),
                {"table": table},
            )
            return {str(row[0]) for row in result.all()}


class TestTheRoutesExposeHistoryAndLineage:
    """§32 — ce que le client (et la future UI) peut lire."""

    @pytest.fixture(autouse=True)
    def _bind(self, db_url: str, monkeypatch: pytest.MonkeyPatch) -> Any:
        """Bind the routes to the test database and to the object-store double."""
        from app.api.middleware.auth_middleware import set_strict_auth_mode

        monkeypatch.setenv("INIS_DATABASE_URL", db_url)
        set_strict_auth_mode(None)
        yield

    def test_the_versions_route_reports_the_current_version_and_the_history(
        self, db_url: str, artifact_like: dict[str, Any], storage: MemoryStorage
    ) -> None:
        import asyncio

        async def bump() -> None:
            engine = create_engine(db_url)
            try:
                await publish_new_version(
                    engine,
                    artifact_like,
                    kind="patch",
                    transformation_ids=["TRF_01M3T0000000000000000000009"],
                )
            finally:
                await engine.dispose()

        asyncio.run(bump())

        response = client.get(f"/v1/artifacts/{artifact_like['artifact_id']}/versions")

        assert response.status_code == 200
        body = response.json()
        assert body["current_version"] == "1.0.1"
        assert [item["version"] for item in body["versions"]] == ["1.0.0", "1.0.1"]
        assert body["versions"][-1]["lineage"]["transformation_ids"] == [
            "TRF_01M3T0000000000000000000009"
        ]
        assert body["versions"][0]["metadata"]["information_ids"] == [
            "INF_01M3T0000000000000000000001"
        ]

    def test_the_lineage_route_shows_the_chain_and_the_deliveries(
        self, db_url: str, artifact_like: dict[str, Any], storage: MemoryStorage
    ) -> None:
        """Le dernier maillon : un téléchargement est enregistré et relu."""
        storage.objects["colis.csv"] = ARTIFACT_BYTES

        downloaded = client.get(f"/v1/artifacts/{artifact_like['artifact_id']}/download")
        assert downloaded.status_code == 200, downloaded.text

        response = client.get(f"/v1/artifacts/{artifact_like['artifact_id']}/lineage")

        assert response.status_code == 200
        body = response.json()
        assert body["artifact_id"] == artifact_like["artifact_id"]
        assert [item["version"] for item in body["versions"]] == ["1.0.0"]
        assert body["versions"][0]["lineage"]["source_ids"] == [
            "SRC_01M3T0000000000000000000001"
        ]
        events = body["delivery_events"]
        assert events and events[-1]["target"] == "http_download"
        assert events[-1]["status"] == "delivered"

    def test_an_unknown_artifact_has_no_history(self, db_url: str) -> None:
        response = client.get(f"/v1/artifacts/{ULID.new('DATA_')}/versions")
        assert response.status_code == 404
