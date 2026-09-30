"""Deterministic §11 information-unit builders (§11, §33.2).

The pipeline and the persistence layer exchange information units as plain
mappings, so the factory returns the same shape the API exposes — not the
20-field pydantic entity. That keeps a factory-built unit insertable through
``InformationUnitRepository`` and comparable with a fetched one.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.domain.value_objects.ulid import ULID

#: The sentence every default unit carries.
DEFAULT_TEXT = "Paris est la capitale de la France et sa plus grande ville."


def _iso_now() -> str:
    """Return the current instant as an ISO-8601 UTC string."""
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def make_information_unit(
    text: str = DEFAULT_TEXT,
    *,
    source_id: str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """Return a valid §11 information unit as a mapping.

    Args:
        text: The unit's ``content["text"]``; two units sharing a text from two
            different sources are the §15.1 cross-source agreement signal.
        source_id: Owning source; a fresh ``SRC_`` ULID when omitted.
        **overrides: Any top-level field of the §11 payload.
    """
    owner = source_id or ULID.new("SRC_")
    url = overrides.pop("url", "https://fr.wikipedia.org/wiki/Paris")
    values: dict[str, Any] = {
        "information_id": ULID.new("INF_"),
        "type": "text",
        "content": {"text": text, "format": "text/plain"},
        "raw_reference": {"url": url, "retrieved_at": _iso_now()},
        "source_id": owner,
        "data_stage": "raw",
        "context": {
            "question": "Quelle est la capitale de la France ?",
            "extraction_method": "wikipedia_extractor",
        },
        "language": "fr",
        "epistemic_status": "factual",
        "provenance": {
            "extracted_from": url,
            "source_id": owner,
            "transformation_ids": [],
        },
        "created_at": _iso_now(),
        "updated_at": _iso_now(),
    }
    values.update(overrides)
    return values

