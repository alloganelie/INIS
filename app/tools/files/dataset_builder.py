"""Shared helpers building :class:`~app.domain.entities.dataset.Dataset` values.

The §21 file readers (``read_csv``, ``read_json``, ``read_xml``, ``read_excel``)
all have to answer the same two questions: *which columns and types does this
payload declare?* and *what is its provenance?*. This module owns that logic so
the readers stay thin and behave identically.

Nothing here invents a value: types are inferred from the values actually
present, and a column whose values are all null is reported as ``null`` rather
than being coerced to a convenient type (§1.2, §0.2).
"""

from __future__ import annotations

from typing import Any

from app.core.errors import ValidationError
from app.domain.entities.dataset import Dataset
from app.domain.value_objects.ulid import ULID

#: Name used to describe an entirely null/empty column.
NULL_TYPE = "null"


def value_type(value: Any) -> str:
    """Return the INIS column type name of *value* (``null`` when absent)."""
    if value is None:
        return NULL_TYPE
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, (dict, list, tuple)):
        return "json"
    text = str(value).strip()
    if not text:
        return NULL_TYPE
    return "string"


def infer_schema(rows: list[dict]) -> dict[str, str]:
    """Infer a ``{column: type}`` schema from the values actually observed.

    Column order follows first appearance. When a column mixes types the
    resulting entry is ``"string"`` only if every non-null value *is* a string;
    otherwise the observed types are joined with ``|`` so the mixed nature is
    visible instead of being silently flattened.
    """
    column_order: list[str] = []
    observed: dict[str, set[str]] = {}

    for row in rows:
        for column, value in row.items():
            if column not in observed:
                observed[column] = set()
                column_order.append(column)
            observed[column].add(value_type(value))

    schema: dict[str, str] = {}
    for column in column_order:
        types = observed[column] - {NULL_TYPE}
        if not types:
            schema[column] = NULL_TYPE
        elif len(types) == 1:
            schema[column] = next(iter(types))
        elif types == {"integer", "number"}:
            schema[column] = "number"
        else:
            schema[column] = "|".join(sorted(types))
    return schema


def normalize_rows(payload: Any) -> list[dict]:
    """Normalize a parsed payload into a list of mapping rows.

    Args:
        payload: A list of mappings, a single mapping, or a scalar.

    Returns:
        One mapping per record.

    Raises:
        ValidationError: If a record is not a mapping (INIS never coerces an
            unreadable shape into a fabricated record).
    """
    if payload is None:
        return []
    if isinstance(payload, dict):
        return [dict(payload)]
    if not isinstance(payload, list):
        return [{"value": payload}]

    rows: list[dict] = []
    for index, record in enumerate(payload):
        if isinstance(record, dict):
            rows.append(dict(record))
            continue
        if isinstance(record, list):
            rows.append({"value": record})
            continue
        raise ValidationError(
            f"record {index} is not a mapping ({type(record).__name__})"
        )
    return rows


def build_dataset(
    rows: list[dict],
    *,
    source_id: str,
    storage_ref: str,
    dataset_id: str | None = None,
) -> Dataset:
    """Build a provenance-complete :class:`Dataset` from parsed *rows*.

    Args:
        rows: Normalized dataset rows.
        source_id: Identifier of the source the payload came from (§0.2).
        storage_ref: Where the payload is persisted (object storage reference
            or local ``file://`` path).
        dataset_id: Optional explicit ``DATA_`` identifier.

    Returns:
        The dataset entity carrying its inferred schema and row count.

    Raises:
        ValidationError: If *source_id* is missing.
    """
    if not source_id or not str(source_id).strip():
        raise ValidationError("source_id is required to build a provenance-complete Dataset")
    return Dataset(
        dataset_id=dataset_id or ULID.new("DATA_"),
        source_id=source_id,
        dataset_schema=infer_schema(rows),
        row_count=len(rows),
        storage_ref=storage_ref,
    )
