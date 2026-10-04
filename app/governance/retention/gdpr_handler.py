"""GDPR rights handler (Art. 15/16/17/20) per §41.9.

* **Erasure (Art. 17)** — pseudonymizes every ``audit_event`` and
  ``information_unit`` bound to an ``actor_id``; records and provenance
  structure are kept, only the identifying value is replaced.
* **Rectification (Art. 16)** — corrects an erroneous unit by superseding
  it with a DERIVED record linked through ``transformation_id``, so the
  traceability chain (§12) is never broken.
* **Portability (Art. 20)** — exports every record linked to a requesting
  agent/actor, grouped by resource type.

Pure in-memory operation over record dicts; persistence stays with the
storage layer.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from datetime import timezone
from typing import Any

from app.domain.value_objects.ulid import ULID
from app.governance.lifecycle.pseudonymizer import Pseudonymizer

Record = dict[str, Any]

ACTOR_FIELD = "actor_id"
AGENT_FIELD = "agent_id"
#: Resource types of the §41.9 portability export (retention keys).
#: ``datasets`` n'y figure **pas** : le vocabulaire §41.9 est celui du bloc
#: ``retention_policies`` de la spec (``audit_events``, ``information_units``,
#: ``pii_data``, ``embeddings``, ``artifacts``) et
#: ``tests/unit/governance/test_gdpr_handler.py`` le garde tel quel. Les données
#: d'un dataset sortent donc par leurs ``information_units`` (leur contenu), pas
#: par une clé inventée ; ``ActorRights.export`` en publie l'inventaire à part.
EXPORTABLE_TYPES: tuple[str, ...] = (
    "audit_events",
    "information_units",
    "pii_data",
    "embeddings",
    "artifacts",
)


#: Champs qui rattachent un enregistrement à un acteur (§41.9) : la demande qu'il
#: a posée, la matière qui en vient, et le propriétaire d'un vecteur. Ce sont les
#: relations réelles du modèle — aucune n'est devinée.
OWNERSHIP_LINKS: tuple[str, ...] = (
    "request_id",
    "document_id",
    "dataset_id",
    "owner_id",
)


class GDPRHandler:
    """Propagate actor erasure as pseudonymization (§41.9)."""

    def __init__(self, pseudonymizer: Pseudonymizer | None = None) -> None:
        self._pseudonymizer = pseudonymizer or Pseudonymizer()

    @property
    def pseudonymizer(self) -> Pseudonymizer:
        """Return the configured pseudonymizer."""
        return self._pseudonymizer

    def erase_actor(
        self,
        actor_id: str,
        audit_events: list[Record],
        information_units: list[Record],
    ) -> dict[str, Any]:
        """Pseudonymize ``actor_id`` in both record lists.

        Returns the transformed copies plus a report; inputs are never
        mutated. Records without a matching ``actor_id`` pass through.
        """
        if not actor_id or not isinstance(actor_id, str):
            raise ValueError("actor_id must be a non-empty string")
        pseudonym = self._pseudonymizer.pseudonymize(actor_id)

        def _scrubbed(records: list[Record]) -> tuple[list[Record], int]:
            scrubbed: list[Record] = []
            updated = 0
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError("records must be dicts")
                copy = dict(record)
                if copy.get(ACTOR_FIELD) == actor_id:
                    copy[ACTOR_FIELD] = pseudonym
                    updated += 1
                scrubbed.append(copy)
            return scrubbed, updated

        clean_events, events_updated = _scrubbed(audit_events)
        clean_units, units_updated = _scrubbed(information_units)
        return {
            "actor_id": actor_id,
            "pseudonym": pseudonym,
            "audit_events": clean_events,
            "information_units": clean_units,
            "audit_events_updated": events_updated,
            "information_units_updated": units_updated,
        }

    def rectify_information_unit(
        self,
        unit: Record,
        *,
        corrected_content: Any,
        transformation_id: str,
        reason: str | None = None,
        new_information_id: str | None = None,
    ) -> dict[str, Any]:
        """Correct an erroneous unit without breaking traceability (Art. 16).

        The original record is kept (marked ``superseded_by``); a copy is
        returned with ``data_stage="derived"`` and the ``transformation_id``
        that produced the correction, linked both ways (§12, §0.2).

        Args:
            unit: the erroneous ``information_unit`` record (dict).
            corrected_content: the corrected ``content`` value.
            transformation_id: id of the transformation applying the fix.
            reason: optional human-readable justification.
            new_information_id: explicit id for the corrected record
                (a fresh ``INF_{ULID}`` is generated when omitted).

        Returns:
            ``{"superseded": <original copy>, "corrected": <new copy>,
            "information_id": old id, "corrected_information_id": new id}``.

        Raises:
            ValueError: on a non-dict unit, missing ``information_id`` or
                empty ``transformation_id``.
        """
        if not isinstance(unit, dict):
            raise ValueError("unit must be a dict")
        old_id = unit.get("information_id")
        if not old_id or not isinstance(old_id, str):
            raise ValueError("unit must carry a non-empty information_id")
        if not transformation_id or not isinstance(transformation_id, str):
            raise ValueError("transformation_id must be a non-empty string")

        corrected_id = new_information_id or ULID.new("INF_")
        if corrected_id == old_id:
            raise ValueError("corrected record must use a new information_id")

        superseded = dict(unit)
        superseded["superseded_by"] = corrected_id
        superseded["superseded_reason"] = reason or "rectification"

        corrected = dict(unit)
        corrected["information_id"] = corrected_id
        corrected["content"] = corrected_content
        corrected["data_stage"] = "derived"
        corrected["transformation_id"] = transformation_id
        corrected["supersedes"] = old_id

        return {
            "information_id": old_id,
            "corrected_information_id": corrected_id,
            "superseded": superseded,
            "corrected": corrected,
        }

    def export_actor_data(
        self,
        actor_id: str,
        *,
        now: datetime | None = None,
        owned_links: Iterable[str] = (),
        **by_type: list[Record],
    ) -> dict[str, Any]:
        """Export every record linked to a requesting agent (Art. 20).

        Records are selected by ``actor_id`` **or** ``agent_id``; a record linked
        to the actor through one of the :data:`OWNERSHIP_LINKS` relations
        (``request_id``, ``document_id``, ``dataset_id``, ``owner_id``) whose
        value is in *owned_links* is selected too. C'est la seule façon d'exporter
        ce qui n'porte pas d'acteur : un artefact appartient à une **demande**,
        une unité à la **matière** dont elle vient, un vecteur à son **unité**.
        Unknown resource types fail explicitly instead of being silently dropped.

        Args:
            actor_id: the requesting agent/actor identifier.
            now: export timestamp (defaults to the current UTC time).
            owned_links: valeurs des liens qui désignent la matière de l'acteur
                (ids de demandes, documents, datasets, unités).
            **by_type: record lists keyed by a §41.9 resource type
                (``audit_events``, ``information_units``, ``pii_data``,
                ``embeddings``, ``artifacts``).

        Returns:
            ``{"actor_id", "exported_at", "counts", "data"}``.

        Raises:
            ValueError: on an empty ``actor_id`` or unknown resource type.
        """
        if not actor_id or not isinstance(actor_id, str):
            raise ValueError("actor_id must be a non-empty string")
        unknown = sorted(set(by_type) - set(EXPORTABLE_TYPES))
        if unknown:
            raise ValueError(
                f"Unknown resource types: {unknown}. Exportable: {list(EXPORTABLE_TYPES)}"
            )
        owned_values = {str(link) for link in owned_links if str(link or "")}

        def _owned(records: list[Record]) -> list[Record]:
            owned: list[Record] = []
            for record in records:
                if not isinstance(record, dict):
                    raise ValueError("records must be dicts")
                if actor_id in (record.get(ACTOR_FIELD), record.get(AGENT_FIELD)) or any(
                    str(record.get(link) or "") in owned_values
                    for link in OWNERSHIP_LINKS
                ):
                    owned.append(dict(record))
            return owned

        moment = now or datetime.now(timezone.utc)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)

        data = {name: _owned(records) for name, records in by_type.items()}
        return {
            "actor_id": actor_id,
            "exported_at": moment.isoformat(),
            "counts": {name: len(records) for name, records in data.items()},
            "data": data,
        }
