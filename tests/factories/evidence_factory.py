"""Deterministic §14.2 evidence builders (§14.2, §33.2).

The shape is the one ``EvidenceRepository.create`` accepts and the one
``GET /v1/evidence/{id}`` returns, so a factory-built record can be persisted
and re-read without translation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.domain.value_objects.ulid import ULID

#: The excerpt every default evidence record quotes.
DEFAULT_EXCERPT = "Paris est la capitale de la France."


def make_evidence(
    *,
    information_id: str | None = None,
    source_id: str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Return a valid §14.2 evidence record as a mapping.

    Args:
        information_id: The unit the excerpt was taken from.
        source_id: The source the excerpt belongs to.
        **overrides: Any field of the §14.2 payload, e.g. ``strength=0.2``.
    """
    values: dict[str, Any] = {
        "evidence_id": ULID.new("EVID_"),
        "claim_id": None,
        "information_id": information_id or ULID.new("INF_"),
        "source_id": source_id or ULID.new("SRC_"),
        "transformation_id": None,
        "excerpt": DEFAULT_EXCERPT,
        "strength": 0.9,
        "confidence": {"score": 0.9},
        "epistemic_status": "fact",
        "provenance": {"extracted_from": "https://fr.wikipedia.org/wiki/Paris"},
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    values.update(overrides)
    return values

