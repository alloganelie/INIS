"""§41.9 — les droits RGPD (Art. 16/17/20) appliqués aux données persistées.

Le raisonnement est déjà écrit (``GDPRHandler``, ``Pseudonymizer``) et le
mécanisme de suppression logique aussi (§18.2, décision ``0016`` : ``deleted_at``
sur les tables de contenu). Ce module est le maillon qui manquait : il lit les
lignes de l'acteur, confie chaque **décision** au ``GDPRHandler`` et écrit le
résultat par les repositories. Il ne réimplémente aucune règle et n'invente
aucune relation : les seuls liens utilisés sont ceux du modèle.

    requests.requester.id  ──▶  requests.request_id
        ├── documents.request_id  ──▶  information_units.document_id
        ├── datasets.request_id   ──▶  information_units.dataset_id
        └── artifacts.request_id
                                        information_units.id ──▶ embeddings.owner_id

Deux conséquences assumées explicitement :

* **Aucune suppression physique** (§0.2 inv. 5). Un document, un dataset ou un
  artefact sort de l'ensemble actif par ``deleted_at`` (§18.2) ; les unités
  extraites suivent le même chemin ; les vecteurs, données **dérivées**, ne sont
  pas supprimés — la recherche cesse de les proposer dès que leur propriétaire
  n'est plus actif, ce qui évite de réécrire l'histoire.
* **Le journal reste lisible.** Une opération écrit un ``audit_event`` (§0.2
  inv. 6) sous le **pseudonyme**, jamais sous l'identité : l'écrire sous
  l'identité réintroduirait exactement la donnée qu'on efface.
"""

from __future__ import annotations

from typing import Any

from app.governance.audit.audit_writer import AuditWriter
from app.governance.retention.gdpr_handler import GDPRHandler
from app.storage.repositories.artifact_repository import ArtifactRepository
from app.storage.repositories.dataset_repository import DatasetRepository
from app.storage.repositories.document_repository import DocumentRepository
from app.storage.repositories.embedding_repository import EmbeddingRepository
from app.storage.repositories.information_unit_repository import InformationUnitRepository
from app.storage.repositories.request_repository import RequestRepository
from app.storage.repositories.version_repository import InformationVersionRepository

__all__ = [
    "ERASURE_ACTION",
    "PORTABILITY_ACTION",
    "RECTIFICATION_ACTION",
    "ActorRights",
]

#: §20 — actions of the trail written by the rights themselves.
ERASURE_ACTION = "gdpr.erasure"
PORTABILITY_ACTION = "gdpr.portability"
RECTIFICATION_ACTION = "gdpr.rectification"

#: §20.1 — the resource an erasure is about.
ACTOR_RESOURCE_TYPE = "actor"


class ActorRights:
    """Applique les droits §41.9 (Art. 16/17/20) aux données réellement stockées.

    Le service ne décide rien : il lit, il appelle le ``GDPRHandler``, il écrit.
    Toutes les règles (pseudonymisation, rectification, périmètre de
    l'export) vivent dans le handler, à un seul endroit.
    """

    def __init__(
        self,
        engine: Any,
        *,
        handler: GDPRHandler | None = None,
        actor_type: str = "agent",
    ) -> None:
        """Bind the service to one engine and one handler.

        Args:
            engine: moteur de base de données.
            handler: le ``GDPRHandler`` qui porte les règles ; un handler neuf
                (avec son ``Pseudonymizer``) quand il est omis.
            actor_type: valeur de ``audit_events.actor_type`` pour les traces
                écrites par les droits (§20.1).
        """
        if engine is None:
            raise ValueError("engine is required: §41.9 rights act on stored rows")
        self._engine = engine
        self._handler = handler or GDPRHandler()
        self._actor_type = actor_type

    @property
    def handler(self) -> GDPRHandler:
        """Return the handler that carries the §41.9 rules."""
        return self._handler

    @staticmethod
    def _require_actor(actor_id: Any) -> str:
        """Return *actor_id* as a non-empty string."""
        text = str(actor_id or "").strip()
        if not text:
            raise ValueError("actor_id must be a non-empty string (§41.9)")
        return text

    async def requests_of(self, actor_id: str) -> list[str]:
        """Return the ids of the requests that name *actor_id* as requester."""
        return await RequestRepository.list_ids_for_actor(self._engine, actor_id)

    async def _write_audit(
        self,
        *,
        action: str,
        pseudonym: str,
        resource_type: str,
        resource_id: str,
        request_id: str,
        reason: str,
    ) -> dict[str, Any]:
        """Write the §20 event of a rights operation, under the pseudonym."""
        return await AuditWriter(self._engine).write(
            {
                "actor_type": self._actor_type,
                "actor_id": pseudonym,
                "action": action,
                "resource_type": resource_type,
                "resource_id": resource_id,
                "request_id": request_id,
                "result": "success",
                "reason": reason,
            }
        )

    async def _scrub_unit_metadata(self, actor_id: str, request_ids: list[str]) -> int:
        """Pseudonymise l'identité là où elle apparaît dans les métadonnées d'unité.

        Les unités rattachées à l'acteur sont lues par la relation réelle
        (``document_id``/``dataset_id`` → ``request_id``) et les deux dictionnaires
        de métadonnées sont passés au **même** ``GDPRHandler.erase_actor`` : la
        règle de pseudonymisation reste à un seul endroit. Rien n'est réécrit
        quand rien n'a changé — une unité n'est pas modifiée « pour la forme ».
        """
        scrubbed = 0
        for request_id in request_ids:
            units = await InformationUnitRepository.list_for_request(self._engine, request_id)
            for unit in units:
                provenance = self._handler.erase_actor(
                    actor_id, [], [dict(unit.get("provenance") or {})]
                )["information_units"][0]
                context = self._handler.erase_actor(
                    actor_id, [], [dict(unit.get("context") or {})]
                )["information_units"][0]
                if provenance == (unit.get("provenance") or {}) and context == (
                    unit.get("context") or {}
                ):
                    continue
                await InformationUnitRepository.update_metadata(
                    self._engine,
                    str(unit["information_id"]),
                    provenance=provenance,
                    context=context,
                )
                scrubbed += 1
        return scrubbed

    @staticmethod
    def _is_withdrawn(record: dict[str, Any]) -> bool:
        """Return whether *record* already left the active set (§18.2)."""
        return bool(record.get("deleted_at")) or (
            str(record.get("status") or "").strip().lower() == "deleted"
        )

    async def erase(self, actor_id: str) -> dict[str, Any]:
        """Art. 17 — efface l'acteur : pseudonymise ce qui l'identifie, retire son contenu actif.

        La propagation suit la chaîne de provenance réelle (§41.9) : les demandes
        de l'acteur, puis leurs documents, datasets et artefacts, puis les unités
        rattachées à ces matières. Aucune ligne n'est supprimée physiquement.

        Args:
            actor_id: l'acteur qui exerce son droit à l'oubli.

        Returns:
            Le rapport de l'opération : pseudonyme, événements réécrits, unités
            pseudonymisées, lignes retirées par type, identifiant de l'événement
            d'audit écrit sous le pseudonyme.
        """
        actor = self._require_actor(actor_id)
        pseudonym = self._handler.pseudonymizer.pseudonymize(actor)
        request_ids = await self.requests_of(actor)

        audit_events = await AuditWriter.pseudonymize_actor(self._engine, actor, pseudonym)
        units_scrubbed = await self._scrub_unit_metadata(actor, request_ids)

        withdrawn = {"documents": 0, "datasets": 0, "artifacts": 0, "information_units": 0}
        for request_id in request_ids:
            for document in await DocumentRepository.list_for_request(self._engine, request_id):
                document_id = str(document["document_id"])
                if await DocumentRepository.soft_delete(self._engine, document_id) is not None:
                    withdrawn["documents"] += 1
                    withdrawn["information_units"] += (
                        await InformationUnitRepository.soft_delete_by_owner(
                            self._engine, document_id=document_id
                        )
                    )
            for dataset in await DatasetRepository.list_for_request(self._engine, request_id):
                dataset_id = str(dataset["dataset_id"])
                if await DatasetRepository.soft_delete(self._engine, dataset_id) is not None:
                    withdrawn["datasets"] += 1
                    withdrawn["information_units"] += (
                        await InformationUnitRepository.soft_delete_by_owner(
                            self._engine, dataset_id=dataset_id
                        )
                    )
            for artifact in await ArtifactRepository.list_for_request(self._engine, request_id):
                if (
                    await ArtifactRepository.soft_delete(
                        self._engine, str(artifact["artifact_id"])
                    )
                    is not None
                ):
                    withdrawn["artifacts"] += 1

        event = await self._write_audit(
            action=ERASURE_ACTION,
            pseudonym=pseudonym,
            resource_type=ACTOR_RESOURCE_TYPE,
            resource_id=pseudonym,
            request_id=request_ids[0] if request_ids else "",
            reason=(
                f"§41.9 Art.17 — {audit_events} audit_event(s) et "
                f"{units_scrubbed} unité(s) pseudonymisé(s) ; "
                + ", ".join(f"{count} {name} retiré(s)" for name, count in withdrawn.items())
            ),
        )
        return {
            "actor_id": actor,
            "pseudonym": pseudonym,
            "requests": request_ids,
            "audit_events_pseudonymized": audit_events,
            "information_units_pseudonymized": units_scrubbed,
            "withdrawn": withdrawn,
            "audit_event": event.get("audit_event_id"),
        }

    async def export(self, actor_id: str) -> dict[str, Any]:
        """Art. 20 — exporter les données de l'acteur, telles qu'elles sont stockées.

        Les enregistrements sont lus par les relations réelles (demandes de
        l'acteur, puis matière, puis unités, puis vecteurs des unités) et le
        **même** ``GDPRHandler.export_actor_data`` construit le colis — c'est le
        format du contrat, pas un second format inventé ici. Une ligne déjà
        retirée de l'ensemble actif (§18.2) n'est pas exportée.

        Args:
            actor_id: l'acteur demandeur.

        Returns:
            Le colis ``{actor_id, exported_at, counts, data, requests,
            audit_event}``.
        """
        actor = self._require_actor(actor_id)
        pseudonym = self._handler.pseudonymizer.pseudonymize(actor)
        request_ids = await self.requests_of(actor)

        audit_events = await AuditWriter.list_events_from_db(self._engine, actor)
        units: list[dict[str, Any]] = []
        datasets: list[dict[str, Any]] = []
        artifacts: list[dict[str, Any]] = []
        documents: list[dict[str, Any]] = []
        for request_id in request_ids:
            units += [
                row
                for row in await InformationUnitRepository.list_for_request(
                    self._engine, request_id
                )
                if not self._is_withdrawn(row)
            ]
            datasets += [
                row
                for row in await DatasetRepository.list_for_request(self._engine, request_id)
                if not self._is_withdrawn(row)
            ]
            artifacts += [
                row
                for row in await ArtifactRepository.list_for_request(self._engine, request_id)
                if not self._is_withdrawn(row)
            ]
            documents += [
                row
                for row in await DocumentRepository.list_for_request(self._engine, request_id)
                if not self._is_withdrawn(row)
            ]

        # §41.9 — les liens réels qui désignent la matière de l'acteur : ce qui
        # n'porte pas d'acteur (artefact, unité, vecteur) s'exporte par eux.
        owned_links: set[str] = set(request_ids)
        for collection, field in (
            (units, "information_id"),
            (datasets, "dataset_id"),
            (documents, "document_id"),
        ):
            owned_links.update(
                str(row[field]) for row in collection if row.get(field)
            )

        embeddings: list[dict[str, Any]] = []
        for unit in units:
            embeddings += await EmbeddingRepository.list_for_owner(
                self._engine, "information_unit", str(unit["information_id"])
            )

        payload = self._handler.export_actor_data(
            actor,
            owned_links=owned_links,
            audit_events=audit_events,
            information_units=units,
            artifacts=artifacts,
            embeddings=embeddings,
        )
        event = await self._write_audit(
            action=PORTABILITY_ACTION,
            pseudonym=pseudonym,
            resource_type=ACTOR_RESOURCE_TYPE,
            resource_id=pseudonym,
            request_id=request_ids[0] if request_ids else "",
            reason=(
                "§41.9 Art.20 — export de "
                f"{sum(payload['counts'].values())} enregistrement(s)"
            ),
        )
        return {
            **payload,
            "requests": request_ids,
            # §41.9 ne définit pas de clé « datasets » pour la portabilité (le
            # vocabulaire est celui des `retention_policies`) : l'inventaire est
            # publié ici, à côté du colis, sans inventer de type d'export. Les
            # données d'un dataset, elles, sortent par leurs ``information_units``.
            "datasets": datasets,
            "audit_event": event.get("audit_event_id"),
        }

    async def rectify_unit(
        self,
        *,
        information_id: str,
        corrected_content: Any,
        transformation_id: str,
        rectified_by: str,
        reason: str | None = None,
        corrected_information_id: str | None = None,
    ) -> dict[str, Any]:
        """Art. 16 — corriger une unité sans casser la traçabilité (§12, §18.1).

        La correction n'écrase **rien** : le ``GDPRHandler`` produit une nouvelle
        unité ``derived`` liée à l'originale (``supersedes``), l'originale reste
        lisible, et sa version courante est marquée ``superseded`` avant qu'une
        version documentant la correction soit ajoutée (§18.1). Les tables
        append-only (``transformations``, ``information_versions``,
        ``audit_events``) ne sont jamais réécrites : une version s'ajoute.

        Args:
            information_id: l'unité erronée.
            corrected_content: le contenu corrigé.
            transformation_id: la transformation qui applique la correction.
            rectified_by: l'opérateur qui rectifie (journalisé sous pseudonyme).
            reason: justification humaine facultative.
            corrected_information_id: identifiant explicite de l'unité corrigée.

        Returns:
            ``{information_id, corrected_information_id, version, audit_event}``.

        Raises:
            ValueError: quand l'unité est inconnue du magasin.
        """
        unit = await InformationUnitRepository.get(self._engine, str(information_id))
        if unit is None:
            raise ValueError(f"unknown information unit: {information_id} (§41.9)")

        report = self._handler.rectify_information_unit(
            unit,
            corrected_content=corrected_content,
            transformation_id=transformation_id,
            reason=reason,
            new_information_id=corrected_information_id,
        )
        corrected = dict(report["corrected"])
        provenance = dict(corrected.get("provenance") or {})
        provenance.update(
            {
                "supersedes": report["information_id"],
                "transformation_id": transformation_id,
                "change_reason": reason or "rectification",
            }
        )
        corrected["provenance"] = provenance

        previous = await InformationVersionRepository.latest(
            self._engine, str(report["information_id"])
        )
        await InformationUnitRepository.create(self._engine, corrected)
        version = await InformationVersionRepository.append(
            self._engine,
            str(report["information_id"]),
            {
                "action": RECTIFICATION_ACTION,
                "superseded_by": corrected["information_id"],
                "reason": reason or "rectification",
                "transformation_id": transformation_id,
            },
        )
        if previous is not None:
            await InformationVersionRepository.mark_superseded(
                self._engine, str(report["information_id"]), int(previous["version"])
            )

        event = await self._write_audit(
            action=RECTIFICATION_ACTION,
            pseudonym=self._handler.pseudonymizer.pseudonymize(self._require_actor(rectified_by)),
            resource_type="information_unit",
            resource_id=str(report["information_id"]),
            request_id=str(provenance.get("request_id") or ""),
            reason=(
                f"§41.9 Art.16 — {report['information_id']} corrigé en "
                f"{report['corrected_information_id']} par {transformation_id}"
            ),
        )
        return {
            "information_id": report["information_id"],
            "corrected_information_id": report["corrected_information_id"],
            "version": version.get("version"),
            "audit_event": event.get("audit_event_id"),
        }
