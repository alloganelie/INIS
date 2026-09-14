"""GDPR right-to-erasure handler (Art. 17) per §41.9.

Erasure pseudonymizes every ``audit_event`` and ``information_unit``
bound to an ``actor_id`` — records and provenance structure are kept,
only the identifying value is replaced. Pure in-memory operation over
record dicts; persistence stays with the storage layer.
"""

from __future__ import annotations

from typing import Any

from app.governance.lifecycle.pseudonymizer import Pseudonymizer

Record = dict[str, Any]

ACTOR_FIELD = "actor_id"


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
