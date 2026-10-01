"""Contre-preuves — le système doit **échouer explicitement**, jamais réussir à tort.

Chaque cas reproduit une panne réelle et vérifie que l'échec est *dit* (limite,
statut, ligne absente) au lieu d'être masqué par une réussite artificielle. Les
cas déjà démontrés ailleurs ne sont pas dupliqués ici : contenu corrompu,
artefact supprimé et accès non autorisé (`tests/api/test_artifact_download_integrity.py`),
interruption et reprise (`tests/integration/test_resume_after_restart.py`),
entrée de cache périmée (`tests/integration/test_cache_l2_postgres.py`),
dataset absent ou d'une mauvaise source (`tests/integration/test_artifact_versions_lineage.py`),
sources contradictoires (`tests/agentic/test_conflict_file_vs_web.py`).

Ce fichier couvre ce qui n'était pas encore prouvé sur le chemin complet :
source injoignable, livraison qui ne peut pas stocker, transformation absente du
contexte, et état en mémoire différent de l'état PostgreSQL après redémarrage.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.v1.requests.pipeline_runner import PipelineRunner, pipeline_runner
from app.domain.value_objects.ulid import ULID
from app.main import app
from app.storage.database.engine import create_engine, set_default_engine
from app.storage.database.session import reset_session_maker
from app.storage.repositories.artifact_repository import ArtifactRepository
from tests.containers import MINIO_BUCKET

client = TestClient(app)

OBJECTIVE = "Analyse adversarialement une requête sans source joignable"
CSV_BYTES = b"city,population\nParis,2145906\nBerlin,3645000\n"
STORAGE_REF = "s3://inis-artifacts/documents/REQ_ADV/villes.csv"


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
def db_configured(db_url: str, monkeypatch: pytest.MonkeyPatch) -> str:
    """Bind the run to the migrated test database."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    reset_session_maker()
    return db_url


class TestAnUnreachableSource:
    """Une source qui ne répond pas : le run le dit, et n'invente rien."""

    def test_the_step_degrades_and_no_unit_is_invented(
        self, db_configured: str, mock_llm: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """La recherche échoue : étape dégradée, limitation, unités du fichier seules."""
        from unittest.mock import AsyncMock

        monkeypatch.setattr(
            "app.connectors.web.provider_router.ProviderRouter.search",
            AsyncMock(side_effect=ConnectionError("fournisseur injoignable")),
        )
        mock_llm.configure('{"summary": "Aucune source web.", "findings": []}')
        request_id = ULID.new("REQ_")

        delivery = asyncio.run(
            PipelineRunner().run(
                request_id,
                {
                    "objective": OBJECTIVE,
                    "request_type": "research",
                    "required_output": {"format": "json"},
                },
            )
        )

        assert delivery["status"] != "completed", (
            "un run sans aucune source joignable ne peut pas être « completed »"
        )
        assert delivery["limitations"], "l'échec doit être dit"
        degraded = [
            step
            for step in delivery.get("steps") or []
            if isinstance(step, dict) and step.get("status") == "degraded"
        ]
        assert degraded or any("recherche" in item.lower() for item in delivery["limitations"]), (
            "la source injoignable doit apparaître comme une étape dégradée ou une limite"
        )
        for unit in delivery["information_units"]:
            assert str(unit.get("source_id") or "").startswith("SRC_"), (
                "aucune unité sans source traçable ne doit être livrée"
            )


class TestAFailedDelivery:
    """Le stockage objet refuse : aucun artefact ne doit se prétendre stocké."""

    def test_the_artifact_says_it_was_not_stored_and_the_download_refuses(
        self, db_configured: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.artifacts.delivery import delivery_service

        class _RefusingStorage:
            """Stockage objet qui refuse toute écriture."""

            def upload(self, key: str, data: bytes, content_type: str | None = None) -> str:
                raise ConnectionError("bucket indisponible")

        monkeypatch.setattr(delivery_service, "build_object_storage", lambda: _RefusingStorage())
        request_id = ULID.new("REQ_")

        outcome = asyncio.run(
            delivery_service.deliver_artifacts(
                request_id=request_id,
                required_output={"format": "json"},
                information_units=[
                    {
                        "information_id": ULID.new("INF_"),
                        "content": {"summary": "une unité"},
                        "source_id": ULID.new("SRC_"),
                    }
                ],
            )
        )

        assert outcome.artifacts, "l'artefact reste décrit, même non stocké"
        record = outcome.artifacts[0]
        assert record["storage_ref"].startswith("unavailable://"), (
            "un fichier non stocké ne doit pas porter une référence de stockage"
        )
        assert any("non stocké" in item for item in outcome.limitations), (
            "la limitation doit nommer le défaut de stockage"
        )
        assert outcome.stored is False

        # Et la route de téléchargement le dit explicitement (503), pas un 200 vide.
        engine = create_engine(db_configured)
        try:
            asyncio.run(ArtifactRepository.create(engine, {**record, "request_id": request_id}))
        finally:
            asyncio.run(engine.dispose())
        response = client.get(f"/v1/artifacts/{record['artifact_id']}/download")
        assert response.status_code == 503
        assert "never stored" in response.json()["detail"]


class TestANonDeliveredTransformation:
    """Aucun `TRF_` n'est cité s'il n'a pas réellement produit les unités livrées."""

    def test_an_unrelated_transformation_is_not_cited(self) -> None:
        """Une transformation dont les sorties ne sont pas livrées est ignorée."""
        from app.artifacts.delivery import delivery_service

        delivered_unit = ULID.new("INF_")
        unrelated = {
            "transformation_id": ULID.new("TRF_"),
            "input_ids": [ULID.new("SRC_")],
            "output_ids": [ULID.new("INF_")],  # une unité qui n'est pas livrée
            "parameters": {"stage": "normalized"},
        }
        related = {
            "transformation_id": ULID.new("TRF_"),
            "input_ids": [ULID.new("SRC_")],
            "output_ids": [delivered_unit],
            "parameters": {"stage": "normalized"},
        }

        assert (
            delivery_service._transformation_ids(
                [unrelated], [{"information_id": delivered_unit}]
            )
            == []
        ), "une transformation sans sortie livrée ne doit pas être citée"
        assert delivery_service._transformation_ids(
            [unrelated, related], [{"information_id": delivered_unit}]
        ) == [related["transformation_id"]]

    def test_no_transformation_context_means_no_citation(self) -> None:
        """Sans contexte de transformation, le lignage reste vide (rien d'inventé)."""
        from app.artifacts.delivery import delivery_service

        assert (
            delivery_service._transformation_ids(
                [], [{"information_id": ULID.new("INF_")}]
            )
            == []
        )
        assert delivery_service._transformation_ids([], []) == []


class TestTheDatabaseIsTheTruthAfterARestart:
    """L'état en mémoire peut disparaître : la base, elle, reste la référence."""

    def test_a_fresh_worker_reads_the_same_artifact_without_duplicating_it(
        self, db_configured: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.artifacts.delivery import delivery_service

        class _MemoryStorage:
            """Stockage en mémoire, adressable par la route de téléchargement."""

            def __init__(self) -> None:
                self.objects: dict[str, bytes] = {}

            def upload(self, key: str, data: bytes, content_type: str | None = None) -> str:
                self.objects[key] = data
                return f"s3://{MINIO_BUCKET}/{key}"

            def download(self, key: str) -> bytes:
                return self.objects[key]

        storage = _MemoryStorage()
        monkeypatch.setattr(delivery_service, "build_object_storage", lambda: storage)
        request_id = ULID.new("REQ_")
        units = [
            {
                "information_id": ULID.new("INF_"),
                "content": {"summary": "unité reproductible"},
                "source_id": ULID.new("SRC_"),
            }
        ]

        async def run_once() -> dict[str, Any]:
            outcome = await delivery_service.deliver_artifacts(
                request_id=request_id,
                required_output={"format": "json"},
                information_units=units,
            )
            return outcome.artifacts[0]

        first = asyncio.run(run_once())

        # « Redémarrage du worker » : tout l'état en mémoire est jeté, y compris
        # celui du singleton du runner.
        pipeline_runner.reset_state()
        assert pipeline_runner.get_state(request_id) is None

        engine = create_engine(db_configured)
        try:
            stored = asyncio.run(ArtifactRepository.get(engine, first["artifact_id"]))
            listed = asyncio.run(ArtifactRepository.list_for_request(engine, request_id))
            counted = asyncio.run(_artifact_count(engine, request_id))
        finally:
            asyncio.run(engine.dispose())

        assert stored is not None, "la base garde l'artefact après la perte de l'état mémoire"
        assert stored["sha256"] == first["sha256"]
        assert [item["artifact_id"] for item in listed] == [first["artifact_id"]]
        assert counted == 1, "aucun doublon après un redémarrage"

        # Et le téléchargement passe toujours par la ligne persistée.
        import importlib

        router_module = importlib.import_module("app.api.v1.artifacts.router")
        monkeypatch.setattr(router_module, "build_object_storage", lambda: storage)
        key = first["storage_ref"].split(f"s3://{MINIO_BUCKET}/", 1)[1]
        response = client.get(f"/v1/artifacts/{first['artifact_id']}/download")
        assert response.status_code == 200
        assert response.content == storage.objects[key]


async def _artifact_count(engine: Any, request_id: str) -> int:
    """Count the artifact rows of one request."""
    async with engine.connect() as conn:
        result = await conn.execute(
            text("SELECT count(*) FROM artifacts WHERE request_id = :value"),
            {"value": request_id},
        )
        return int(result.scalar_one())
