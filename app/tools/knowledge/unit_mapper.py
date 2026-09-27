"""Map a stored ``information_units`` row onto the §11 domain entity.

The PostgreSQL table only materialises the columns §27 mandates; the remaining
§11 fields are reconstructed with explicit defaults. Nothing is invented: when
the row carries no ``source_id`` the mapping raises, because an
``InformationUnit`` without a source cannot satisfy the provenance invariant
(§0.2, §11).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.core.errors import ValidationError
from app.domain.entities.information_unit import InformationUnit

__all__ = ["information_unit_from_row"]

#: Columns that may be read from an ``information_units`` row.
_JSON_COLUMNS = ("location", "context", "time", "classification", "quality", "confidence", "provenance")
_DEFAULT_STAGE = "raw"


def _as_mapping(value: Any) -> dict:
    """Return a mapping, or an empty mapping when the value is absent/opaque."""
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _as_timestamp(value: Any) -> datetime:
    """Return *value* as a timezone-aware UTC datetime, defaulting to now."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(UTC)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)


def information_unit_from_row(
    row: Mapping[str, Any],
    *,
    extra_provenance: Mapping[str, Any] | None = None,
) -> InformationUnit:
    """Build an :class:`InformationUnit` from one stored database row.

    Args:
        row: A mapping produced by a ``SELECT`` on ``information_units``.
        extra_provenance: Retrieval metadata merged into ``provenance`` (for
            example the similarity score or the retrieval mode), so the way a
            unit was found stays traceable (§14.1).

    Returns:
        The reconstructed information unit.

    Raises:
        ValidationError: If the row carries no ``information_id`` or no
            ``source_id``.
    """
    information_id = row.get("information_id") or row.get("id")
    if not information_id:
        raise ValidationError("information_units row is missing its identifier")
    source_id = row.get("source_id")
    if not source_id:
        raise ValidationError(
            f"information unit {information_id} carries no source_id (§0.2)"
        )

    provenance = _as_mapping(row.get("provenance"))
    if extra_provenance:
        provenance.update({str(key): value for key, value in extra_provenance.items()})

    payload: dict[str, Any] = {
        "information_id": str(information_id),
        "type": str(row.get("type") or "text"),
        "content": _as_mapping(row.get("content")),
        "raw_reference": _as_mapping(row.get("raw_reference")),
        "source_id": str(source_id),
        "document_id": row.get("document_id") or None,
        "dataset_id": row.get("dataset_id") or None,
        "language": row.get("language") or None,
        "unit": row.get("unit") or None,
        "data_stage": str(row.get("data_stage") or _DEFAULT_STAGE),
        "versions": list(row.get("versions") or []),
        "created_at": _as_timestamp(row.get("created_at")),
        "updated_at": _as_timestamp(row.get("updated_at") or row.get("created_at")),
        "provenance": provenance,
    }
    for column in _JSON_COLUMNS:
        if column == "provenance":
            continue
        payload[column] = _as_mapping(row.get(column))

    return InformationUnit(**payload)
