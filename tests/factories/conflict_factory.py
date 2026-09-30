"""Deterministic ``Conflict`` builders (§14.3, §33.2)."""

from __future__ import annotations

from typing import Any

from app.domain.entities.conflict import Conflict
from app.domain.value_objects.ulid import ULID


def make_conflict(
    *,
    information_a: str | None = None,
    information_b: str | None = None,
    **overrides: Any,
) -> Conflict:
    """Return a valid :class:`~app.domain.entities.conflict.Conflict`.

    Args:
        information_a: First contradicting unit.
        information_b: Second contradicting unit.
        **overrides: Any ``Conflict`` field, e.g. ``severity="high"`` or
            ``resolution_status="resolved"``.
    """
    values: dict[str, Any] = {
        "conflict_id": ULID.new("CONFLICT_"),
        "information_a": information_a or ULID.new("INF_"),
        "information_b": information_b or ULID.new("INF_"),
        "difference_type": "value",
        "severity": "medium",
        "resolution_status": "open",
        "resolution_evidence": [],
    }
    values.update(overrides)
    return Conflict(**values)

