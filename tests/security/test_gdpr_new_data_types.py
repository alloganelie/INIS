"""§41.9 — les droits RGPD sur les **nouvelles** catégories de données.

Le plan demandait de **vérifier**, pas d'affirmer : datasets, artefacts et
embeddings répondent-ils au droit à l'oubli (Art. 17), à la portabilité
(Art. 20) et à la rectification (Art. 16) — et un artefact supprimé au titre du
RGPD est-il réellement intéléchargeable ?

Tout est exercé sur de **vraies** lignes PostgreSQL (fixture ``db_url``) :

* les droits passent par ``ActorRights``, le service qui applique les règles du
  ``GDPRHandler`` aux lignes stockées (§18.2 pour le retrait, ``deleted_at``) ;
* les refus sont mesurés sur la **route HTTP réelle** de téléchargement
  (``GET /v1/artifacts/{id}/download``) et sur les chemins de contournement
  réellement exposés (``GET`` simple, ``/versions``, liste) ;
* la recherche est interrogée sur le vrai ``HybridSearch`` avec un vrai vecteur
  ``pgvector``, pour prouver qu'un embedding dont la donnée source est retirée
  ne « continue pas à servir » en silence.

Ce que ce fichier ne fait pas : il n'invente aucune clé de portabilité pour
``datasets`` (§41.9 n'en définit pas, et
``tests/unit/governance/test_gdpr_handler.py`` épingle le vocabulaire) et il ne
supprime jamais physiquement une ligne gouvernée — le retrait est celui du
contrat, ``deleted_at``.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.domain.value_objects.ulid import ULID
from app.governance.audit.audit_writer import AuditWriter
from app.governance.retention.actor_rights import ActorRights
from app.main import app
from app.storage.database.engine import create_engine, set_default_engine
from app.storage.repositories.artifact_repository import ArtifactRepository
from app.storage.repositories.dataset_repository import DatasetRepository
from app.storage.repositories.document_repository import DocumentRepository
from app.storage.repositories.embedding_repository import EmbeddingRepository
from app.storage.repositories.information_unit_repository import InformationUnitRepository
from app.storage.repositories.request_repository import RequestRepository
from app.storage.repositories.source_repository import SourceRepository
from app.storage.repositories.version_repository import InformationVersionRepository
from app.storage.search.hybrid_search import HybridSearch

#: Acteurs du test. Distinctifs à dessein : leur disparition du journal se
#: vérifie par simple recherche de chaîne (aucune donnée personnelle réelle).
ACTOR = "AGT_L83_GDPR"
OPERATOR = "OPR_L83_GDPR"

#: Un mot rare, propre à ce module : la recherche ne peut ramener que nos lignes.
TOKEN = "zorglubification"

#: Dimension du vecteur de test (§16.1 : ``vector(1536)``).
VECTOR = [0.0] * 1535 + [1.0]


def _uid(prefix: str) -> str:
    """Return a fresh identifier in this module's own namespace."""
    return prefix + ULID.new("REQ_").removeprefix("REQ_")


async def _seed_request(engine: Any, request_id: str, actor_id: str = ACTOR) -> None:
    """Store one §7 request whose ``requester.id`` names *actor_id*."""
    await RequestRepository.create(
        engine,
        {
            "request_id": request_id,
            "request_type": "data",
            "objective": f"§41.9 — {TOKEN}",
            "requester": {"type": "agent", "id": actor_id},
            "status": "completed",
        },
    )


async def _seed_material(
    engine: Any,
    request_id: str,
    *,
    unit_text: str | None = None,
    with_embedding: bool = False,
) -> dict[str, str]:
    """Store one document + dataset + artifact + unit for *request_id*."""
    source_id = _uid("SRC_")
    document_id, dataset_id = _uid("DOC_"), _uid("DS_")
    unit_id, artifact_id = _uid("INF_"), _uid("ART_2026_")
    await SourceRepository.create(
        engine, {"source_id": source_id, "source_type": "internal", "name": TOKEN}
    )
    await DocumentRepository.create(
        engine,
        {
            "document_id": document_id,
            "source_id": source_id,
            "mime_type": "text/plain",
            "content_hash": hashlib.sha256(document_id.encode()).hexdigest(),
            "storage_ref": f"s3://inis-documents/{document_id}.txt",
            "request_id": request_id,
            "file_name": f"{TOKEN}.txt",
        },
    )
    await DatasetRepository.create(
        engine,
        {
            "dataset_id": dataset_id,
            "name": f"{TOKEN}.txt",
            "source_id": source_id,
            "row_count": 1,
            "request_id": request_id,
            "storage_ref": f"s3://inis-datasets/{dataset_id}",
        },
    )
    await InformationUnitRepository.create(
        engine,
        {
            "information_id": unit_id,
            "type": "text",
            "content": {"text": unit_text or f"{TOKEN} — une information"},
            "source_id": source_id,
            "document_id": document_id,
            "dataset_id": dataset_id,
            "data_stage": "normalized",
            "provenance": {"document_id": document_id, "request_id": request_id},
            "context": {"request_id": request_id},
        },
    )
    await ArtifactRepository.create(
        engine,
        {
            "artifact_id": artifact_id,
            "artifact_type": "dataset",
            "file_name": f"{TOKEN}.csv",
            "mime_type": "text/csv",
            "version": "1.0.0",
            "size_bytes": 8,
            "sha256": hashlib.sha256(b"a,b\n1,2\n").hexdigest(),
            "storage_ref": f"s3://inis-artifacts/{artifact_id}.csv",
            "purpose": "livraison",
            "source_ids": [source_id],
            "dataset_ids": [dataset_id],
            "transformation_ids": [],
            "provenance_complete": True,
            "status": "available",
            "request_id": request_id,
        },
    )
    if with_embedding:
        await EmbeddingRepository.insert_many(
            engine,
            [
                {
                    "owner_type": "information_unit",
                    "owner_id": unit_id,
                    "model": "test-embedding",
                    "vector": VECTOR,
                }
            ],
        )
    return {
        "source_id": source_id,
        "document_id": document_id,
        "dataset_id": dataset_id,
        "information_id": unit_id,
        "artifact_id": artifact_id,
    }


async def _purge(engine: Any, ids: dict[str, str]) -> None:
    """Remove every row **this module** created, so the shared tables stay as found.

    Le retrait descend la chaîne avant de remonter (vecteur, versions, unité,
    artefact, dataset, document, demande, source) et emporte aussi les unités
    **dérivées** d'une rectification : elles portent le même ``document_id`` que
    l'originale, donc ``ids`` ne suffirait pas à les nommer. Aucune ligne
    préexistante ne peut être touchée : tous ces identifiants sont neufs (ULID).
    """
    parameters = {
        "unit": ids.get("information_id"),
        "document": ids.get("document_id"),
        "dataset": ids.get("dataset_id"),
        "artifact": ids.get("artifact_id"),
        "request": ids.get("request_id"),
        "source": ids.get("source_id"),
    }
    statements = (
        (
            "DELETE FROM embeddings WHERE owner_id IN ("
            "  SELECT id FROM information_units WHERE id = :unit"
            "  OR document_id = :document OR dataset_id = :dataset)"
        ),
        (
            "DELETE FROM information_versions WHERE information_id = :unit"
            " OR information_id IN ("
            "  SELECT id FROM information_units WHERE document_id = :document"
            "  OR dataset_id = :dataset)"
        ),
        (
            "DELETE FROM information_units WHERE id = :unit"
            " OR document_id = :document OR dataset_id = :dataset"
        ),
        "DELETE FROM artifacts WHERE artifact_id = :artifact",
        "DELETE FROM datasets WHERE dataset_id = :dataset",
        "DELETE FROM documents WHERE id = :document",
        "DELETE FROM requests WHERE request_id = :request",
        "DELETE FROM sources WHERE id = :source",
    )
    async with engine.begin() as conn:
        for statement in statements:
            await conn.execute(text(statement), parameters)
        await conn.execute(
            text("DELETE FROM audit_events WHERE actor_id IN (:pseudonym, :operator)"),
            {
                "pseudonym": ActorRights(engine).handler.pseudonymizer.pseudonymize(ACTOR),
                "operator": ActorRights(engine).handler.pseudonymizer.pseudonymize(OPERATOR),
            },
        )


@pytest.fixture
async def engine(db_url: str) -> Any:
    """A real engine on the migrated schema, torn down after the test."""
    created = create_engine(db_url)
    try:
        yield created
    finally:
        await created.dispose()


class TestRightToForget:
    """Art. 17 — la suppression se propage dans la chaîne, sans effacer l'histoire."""

    async def test_a_dataset_and_its_units_leave_the_active_set(self, engine: Any) -> None:
        """Le dataset de l'acteur et les unités qui en viennent sont retirés (§18.2)."""
        request_id = _uid("REQ_")
        await _seed_request(engine, request_id)
        ids = await _seed_material(engine, request_id)
        try:
            report = await ActorRights(engine).erase(ACTOR)

            dataset = await DatasetRepository.get(engine, ids["dataset_id"])
            document = await DocumentRepository.get(engine, ids["document_id"])
            unit = await InformationUnitRepository.get(engine, ids["information_id"])
            assert dataset is not None and dataset["deleted_at"]
            assert document is not None and document["deleted_at"]
            assert unit is not None and unit["deleted_at"]
            assert report["withdrawn"]["datasets"] == 1
            assert report["withdrawn"]["documents"] == 1
            assert report["withdrawn"]["information_units"] == 1
        finally:
            await _purge(engine, {**ids, "request_id": request_id})

    async def test_the_withdrawn_rows_stay_readable(self, engine: Any) -> None:
        """Aucune suppression physique : la ligne retirée reste explicable (§18.2)."""
        request_id = _uid("REQ_")
        await _seed_request(engine, request_id)
        ids = await _seed_material(engine, request_id)
        try:
            await ActorRights(engine).erase(ACTOR)

            dataset = await DatasetRepository.get(engine, ids["dataset_id"])
            assert dataset is not None, "le dataset retiré reste lisible"
            assert dataset["request_id"] == request_id
            assert dataset["storage_ref"]
        finally:
            await _purge(engine, {**ids, "request_id": request_id})

    async def test_the_audit_trail_is_pseudonymized_not_erased(self, engine: Any) -> None:
        """§41.9 — l'identité est remplacée, la structure du journal est conservée."""
        request_id = _uid("REQ_")
        await _seed_request(engine, request_id)
        ids = await _seed_material(engine, request_id)
        writer = AuditWriter(engine)
        await writer.write(
            {
                "actor_type": "agent",
                "actor_id": ACTOR,
                "action": "search",
                "resource_type": "request",
                "resource_id": request_id,
                "request_id": request_id,
                "result": "success",
                "reason": "preuve §41.9",
            }
        )
        try:
            pseudonym = ActorRights(engine).handler.pseudonymizer.pseudonymize(ACTOR)
            report = await ActorRights(engine).erase(ACTOR)

            assert report["audit_events_pseudonymized"] == 1
            assert await AuditWriter.list_events_from_db(engine, ACTOR) == []
            events = await AuditWriter.list_events_from_db(engine, pseudonym)
            assert [event["action"] for event in events] == ["search", "gdpr.erasure"]
            # La structure de provenance est intacte : ressource, demande, résultat.
            first = events[0]
            assert first["resource_id"] == request_id
            assert first["result"] == "success"
        finally:
            await _purge(engine, {**ids, "request_id": request_id})

    async def test_a_withdrawn_unit_is_not_given_a_new_vector(self, engine: Any) -> None:
        """Un vecteur ne se calcule pas pour une donnée retirée (§16.1, §18.2)."""
        request_id = _uid("REQ_")
        await _seed_request(engine, request_id)
        ids = await _seed_material(engine, request_id)
        try:
            missing_before = await EmbeddingRepository.list_units_without_embedding(
                engine, request_id=request_id, data_stages=("normalized",)
            )
            assert ids["information_id"] in [row["information_id"] for row in missing_before]

            await ActorRights(engine).erase(ACTOR)

            missing_after = await EmbeddingRepository.list_units_without_embedding(
                engine, request_id=request_id, data_stages=("normalized",)
            )
            assert ids["information_id"] not in [row["information_id"] for row in missing_after]
        finally:
            await _purge(engine, {**ids, "request_id": request_id})

    async def test_an_erasure_is_idempotent(self, engine: Any) -> None:
        """Deux demandes successives ne comptent pas deux fois le même retrait."""
        request_id = _uid("REQ_")
        await _seed_request(engine, request_id)
        ids = await _seed_material(engine, request_id)
        try:
            first = await ActorRights(engine).erase(ACTOR)
            second = await ActorRights(engine).erase(ACTOR)

            assert first["withdrawn"]["datasets"] == 1
            assert second["withdrawn"]["datasets"] == 0
            assert second["withdrawn"]["artifacts"] == 0
            assert second["pseudonym"] == first["pseudonym"]
        finally:
            await _purge(engine, {**ids, "request_id": request_id})

    async def test_an_empty_actor_is_refused(self, engine: Any) -> None:
        """Un effacement sans acteur n'efface rien : il est refusé (§41.9)."""
        with pytest.raises(ValueError, match="actor_id"):
            await ActorRights(engine).erase("  ")


def _on_its_own_loop(db_url: str, coroutine_factory: Any) -> Any:
    """Run one DB operation on its own loop and its own engine.

    Chaque appel ouvre sa boucle et dispose son moteur : un pool asyncpg
    appartient à la boucle qui l'a ouvert (piège P14), donc rien n'est conservé
    entre l'amorçage (``asyncio.run``) et la requête HTTP (la boucle de
    ``TestClient``).
    """

    async def _run() -> Any:
        engine = create_engine(db_url)
        try:
            return await coroutine_factory(engine)
        finally:
            await engine.dispose()

    return asyncio.run(_run())


def _prepare(db_url: str) -> dict[str, str]:
    """Seed one actor's request, material and artifact; return every id."""

    async def _seed(engine: Any) -> dict[str, str]:
        request_id = _uid("REQ_")
        await _seed_request(engine, request_id)
        return {**await _seed_material(engine, request_id), "request_id": request_id}

    return _on_its_own_loop(db_url, _seed)


def _erase(db_url: str) -> dict[str, Any]:
    """Exercise the Art. 17 right of ``ACTOR`` against the real store."""
    return _on_its_own_loop(db_url, lambda engine: ActorRights(engine).erase(ACTOR))


@pytest.fixture
def wired_app(db_url: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Point the running app at the test database, and forget it afterwards."""
    monkeypatch.setenv("INIS_DATABASE_URL", db_url)
    set_default_engine(None)
    yield
    set_default_engine(None)


class TestArtifactIsRefusedAfterAGDPRErasure:
    """Art. 17 — un artefact retiré ne se télécharge plus, par aucun chemin ouvert."""

    def test_the_download_is_refused_after_the_erasure(
        self, db_url: str, wired_app: Any
    ) -> None:
        """La route de téléchargement répond 410 : l'artefact existait, il est parti."""
        ids = _prepare(db_url)
        client = TestClient(app)
        try:
            listed = client.get(f"/v1/artifacts?request_id={ids['request_id']}")
            assert [
                row["artifact_id"] for row in listed.json()["artifacts"]
            ] == [ids["artifact_id"]], "avant l'effacement, l'artefact est bien livré"

            _erase(db_url)

            refused = client.get(f"/v1/artifacts/{ids['artifact_id']}/download")
            assert refused.status_code == 410
            assert "gone" in refused.json()["detail"].lower()
        finally:
            _on_its_own_loop(db_url, lambda engine: _purge(engine, ids))

    def test_every_exposed_path_refuses_it(
        self, db_url: str, wired_app: Any
    ) -> None:
        """Contournement : détail, versions et liste refusent aussi (§18.2)."""
        ids = _prepare(db_url)
        client = TestClient(app)
        try:
            _erase(db_url)

            artifact_id = ids["artifact_id"]
            assert client.get(f"/v1/artifacts/{artifact_id}").status_code == 410
            assert client.get(f"/v1/artifacts/{artifact_id}/versions").status_code == 410
            assert client.get(f"/v1/artifacts/{artifact_id}/download").status_code == 410
            listed = client.get(f"/v1/artifacts?request_id={ids['request_id']}")
            payload = listed.json()
            assert payload["artifacts"] == []
            assert payload["total"] == 0

            # §18.2/§20 — le corps ne dit rien (il ne doit pas révéler l'existence
            # de la donnée retirée), la raison est dans le journal.
            events = _on_its_own_loop(
                db_url, lambda engine: AuditWriter.list_events_from_db(engine)
            )
            reasons = " ".join(str(event.get("reason") or "") for event in events)
            assert "filtered out of the list" in reasons
        finally:
            _on_its_own_loop(db_url, lambda engine: _purge(engine, ids))


class TestPortability:
    """Art. 20 — l'export part des lignes réellement stockées."""

    async def test_the_export_carries_the_actors_records(self, engine: Any) -> None:
        """Chaque catégorie stockée de l'acteur sort, avec son identité et ses métadonnées."""
        request_id = _uid("REQ_")
        await _seed_request(engine, request_id)
        ids = await _seed_material(engine, request_id, with_embedding=True)
        try:
            export = await ActorRights(engine).export(ACTOR)

            assert export["actor_id"] == ACTOR
            assert export["requests"] == [request_id]
            assert export["counts"]["information_units"] == 1
            assert export["counts"]["artifacts"] == 1
            assert export["counts"]["embeddings"] == 1
            unit = export["data"]["information_units"][0]
            assert unit["information_id"] == ids["information_id"]
            assert unit["provenance"]["request_id"] == request_id
            assert export["data"]["artifacts"][0]["artifact_id"] == ids["artifact_id"]
            assert export["data"]["artifacts"][0]["sha256"]
            assert export["data"]["embeddings"][0]["owner_id"] == ids["information_id"]
        finally:
            await _purge(engine, {**ids, "request_id": request_id})

    async def test_a_withdrawn_record_is_not_exported(self, engine: Any) -> None:
        """Ce qui a été retiré de l'ensemble actif n'est plus exporté (§18.2, §41.9)."""
        request_id = _uid("REQ_")
        await _seed_request(engine, request_id)
        ids = await _seed_material(engine, request_id)
        try:
            await ActorRights(engine).erase(ACTOR)
            export = await ActorRights(engine).export(ACTOR)

            assert export["counts"]["artifacts"] == 0
            assert export["counts"]["information_units"] == 0
            assert export["data"]["artifacts"] == []
        finally:
            await _purge(engine, {**ids, "request_id": request_id})

    async def test_the_datasets_are_reported_beside_the_payload(self, engine: Any) -> None:
        """§41.9 ne définit pas de clé ``datasets`` : l'inventaire est publié à part."""
        request_id = _uid("REQ_")
        await _seed_request(engine, request_id)
        ids = await _seed_material(engine, request_id)
        try:
            export = await ActorRights(engine).export(ACTOR)

            assert [row["dataset_id"] for row in export["datasets"]] == [ids["dataset_id"]]
            assert "datasets" not in export["counts"], (
                "le vocabulaire de portabilité reste celui du contrat"
            )
        finally:
            await _purge(engine, {**ids, "request_id": request_id})

    async def test_the_export_writes_an_audit_event(self, engine: Any) -> None:
        """§0.2 inv. 6 — un export s'inscrit au journal, sous le pseudonyme."""
        request_id = _uid("REQ_")
        await _seed_request(engine, request_id)
        ids = await _seed_material(engine, request_id)
        try:
            pseudonym = ActorRights(engine).handler.pseudonymizer.pseudonymize(ACTOR)
            export = await ActorRights(engine).export(ACTOR)

            events = await AuditWriter.list_events_from_db(engine, pseudonym)
            assert [event["action"] for event in events] == ["gdpr.portability"]
            assert export["audit_event"] == events[0]["audit_event_id"]
            assert ACTOR not in json.dumps(events, default=str)
        finally:
            await _purge(engine, {**ids, "request_id": request_id})


class TestRectification:
    """Art. 16 — corriger sans casser la traçabilité (§12, §18.1)."""

    async def test_a_corrected_unit_is_a_new_derived_record(self, engine: Any) -> None:
        """L'originale reste, la correction est une unité ``derived`` qui la remplace."""
        request_id = _uid("REQ_")
        await _seed_request(engine, request_id)
        ids = await _seed_material(engine, request_id)
        try:
            report = await ActorRights(engine).rectify_unit(
                information_id=ids["information_id"],
                corrected_content={"text": f"{TOKEN} — corrigé"},
                transformation_id="TRF_L83_RECTIF",
                rectified_by=OPERATOR,
                reason="valeur erronée",
            )

            corrected = await InformationUnitRepository.get(
                engine, report["corrected_information_id"]
            )
            original = await InformationUnitRepository.get(engine, ids["information_id"])
            assert corrected is not None and corrected["data_stage"] == "derived"
            assert corrected["provenance"]["supersedes"] == ids["information_id"]
            assert corrected["provenance"]["transformation_id"] == "TRF_L83_RECTIF"
            assert original is not None, "l'originale reste récupérable (§0.2 inv. 4)"
            assert original["provenance"]["document_id"] == ids["document_id"]
            assert original["content"]["text"].endswith("une information")
        finally:
            await _purge(engine, {**ids, "request_id": request_id})

    async def test_the_previous_version_is_superseded(self, engine: Any) -> None:
        """§18.1 — une version remplacée est marquée ``superseded``, jamais effacée."""
        request_id = _uid("REQ_")
        await _seed_request(engine, request_id)
        ids = await _seed_material(engine, request_id)
        try:
            await InformationVersionRepository.append(
                engine, ids["information_id"], {"content": {"text": f"{TOKEN} — v1"}}
            )
            report = await ActorRights(engine).rectify_unit(
                information_id=ids["information_id"],
                corrected_content={"text": f"{TOKEN} — corrigé"},
                transformation_id="TRF_L83_RECTIF",
                rectified_by=OPERATOR,
            )

            versions = await InformationVersionRepository.list_for(
                engine, ids["information_id"]
            )
            assert [version["superseded"] for version in versions] == [True, False]
            assert versions[-1]["content"]["action"] == "gdpr.rectification"
            assert (
                versions[-1]["content"]["superseded_by"] == report["corrected_information_id"]
            )
            assert report["version"] == versions[-1]["version"]
        finally:
            await _purge(engine, {**ids, "request_id": request_id})

    async def test_an_unknown_unit_is_refused(self, engine: Any) -> None:
        """Rectifier une unité inexistante échoue explicitement (§25.2)."""
        with pytest.raises(ValueError, match="unknown information unit"):
            await ActorRights(engine).rectify_unit(
                information_id="INF_CONNUE_DE_PERSONNE",
                corrected_content={"text": "x"},
                transformation_id="TRF_L83_RECTIF",
                rectified_by=OPERATOR,
            )


class TestEmbeddingsInSearch:
    """Un vecteur dont la donnée source est retirée ne doit plus servir (§41.9)."""

    async def test_a_withdrawn_source_is_not_returned_by_the_search(
        self, engine: Any, db_url: str
    ) -> None:
        """Recherche hybride réelle : le vecteur reste, la réponse ne le propose plus."""
        request_id = _uid("REQ_")
        await _seed_request(engine, request_id)
        ids = await _seed_material(engine, request_id, with_embedding=True)
        search = HybridSearch(db_url)
        try:
            before = await search.search(query=TOKEN, query_vector=VECTOR, limit=10)
            assert ids["information_id"] in [row["owner_id"] for row in before]

            await DatasetRepository.soft_delete(engine, ids["dataset_id"])
            await InformationUnitRepository.soft_delete_by_owner(
                engine, dataset_id=ids["dataset_id"]
            )

            after = await search.search(query=TOKEN, query_vector=VECTOR, limit=10)
            assert ids["information_id"] not in [row["owner_id"] for row in after]
            # Le vecteur n'est pas supprimé : §0.2 interdit la suppression physique.
            assert await EmbeddingRepository.list_for_owner(
                engine, "information_unit", ids["information_id"]
            )
        finally:
            await _purge(engine, {**ids, "request_id": request_id})
