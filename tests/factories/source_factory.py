"""Deterministic ``Source`` builders (§9, §33.2)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.domain.entities.source import Source
from app.domain.value_objects.ulid import ULID

#: A stable, resolvable URL so assertions can be written against a constant.
DEFAULT_URL = "https://fr.wikipedia.org/wiki/Paris"


def make_source(**overrides: Any) -> Source:
    """Return a valid §9 :class:`~app.domain.entities.source.Source`.

    Args:
        **overrides: Any ``Source`` field, e.g. ``reliability_score=0.2`` to
            build a low-trust source for a §15 reliability scenario.
    """
    values: dict[str, Any] = {
        "source_id": ULID.new("SRC_"),
        "type": "web",
        "url": DEFAULT_URL,
        "reliability_score": 0.8,
        "freshness": {
            "checked_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "max_age_hours": 24,
        },
    }
    values.update(overrides)
    return Source(**values)


def make_source_create_payload(**overrides: Any) -> dict[str, Any]:
    """Return a ``POST /v1/sources`` payload (§32 ``SourceCreate``)."""
    payload: dict[str, Any] = {
        "name": "Wikipedia — Paris",
        "source_type": "web",
        "url": DEFAULT_URL,
        "description": "Encyclopaedic article used as a reference source.",
        "trust_level": 0.8,
        "metadata": {"provider": "wikipedia"},
    }
    payload.update(overrides)
    return payload

