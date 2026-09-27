"""``read_json`` internal tool per §21.

Nested objects are preserved as ``json``-typed columns; INIS never flattens or
drops a nested structure to make a table look tidy (§0.2).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.core.errors import InfrastructureError, ValidationError
from app.domain.entities.dataset import Dataset
from app.tools.files.dataset_builder import build_dataset, normalize_rows

__all__ = ["read_json", "load_json"]


def load_json(
    path: str,
    *,
    source_id: str,
    records_key: str | None = None,
) -> tuple[Dataset, list[dict]]:
    """Parse the JSON file at *path* and return its dataset together with its rows.

    Args:
        path: Path of the JSON file.
        source_id: Identifier of the source the file belongs to (§0.2).
        records_key: When the document wraps its records in an object (e.g.
            ``{"results": [...]}``), the key to read them from.

    Returns:
        ``(dataset, rows)``.

    Raises:
        ValidationError: If the file is missing or *records_key* is unknown.
        InfrastructureError: If the payload is not valid JSON.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise ValidationError(f"json file not found: {path}")

    try:
        payload = json.loads(file_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise InfrastructureError(f"invalid JSON payload: {exc}") from exc

    if records_key is not None:
        if not isinstance(payload, dict) or records_key not in payload:
            raise ValidationError(f"records_key '{records_key}' not found in JSON payload")
        payload = payload[records_key]

    rows = normalize_rows(payload)
    return (
        build_dataset(rows, source_id=source_id, storage_ref=file_path.resolve().as_uri()),
        rows,
    )


def read_json(path: str, *, source_id: str, records_key: str | None = None) -> Dataset:
    """Return the §21 ``Dataset`` read from the JSON file at *path*."""
    dataset, _rows = load_json(path, source_id=source_id, records_key=records_key)
    return dataset
