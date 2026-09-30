"""Deterministic ``Dataset`` builders (§9, §33.2)."""

from __future__ import annotations

from typing import Any

from app.domain.entities.dataset import Dataset
from app.domain.value_objects.ulid import ULID

#: The schema every default dataset declares.
DEFAULT_SCHEMA: dict[str, str] = {
    "city": "string",
    "population": "integer",
}


def make_dataset(
    *,
    source_id: str | None = None,
    rows: int = 2,
    **overrides: Any,
) -> Dataset:
    """Return a valid :class:`~app.domain.entities.dataset.Dataset`.

    Args:
        source_id: The source the dataset came from.
        rows: ``row_count`` — the factory never invents a row count that
            contradicts the schema it declares (§13 completeness).
        **overrides: Any ``Dataset`` field.
    """
    values: dict[str, Any] = {
        "dataset_id": ULID.new("DATA_"),
        "source_id": source_id or ULID.new("SRC_"),
        "dataset_schema": dict(DEFAULT_SCHEMA),
        "row_count": rows,
        "storage_ref": "s3://inis-datasets/test/dataset.parquet",
    }
    values.update(overrides)
    return Dataset(**values)

