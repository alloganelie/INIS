"""Tabular projection rules shared by the CSV and XLSX generators (§24.3).

Both tabular formats must agree on two things, otherwise the same delivery
exports differently depending on the format the client asked for:

* the text of a cell — a nested value keeps its canonical JSON text, ``None``
  becomes an empty cell and a boolean keeps its machine-readable spelling
  rather than ``True``/``False``;
* the column order — the sorted union of the row keys, so the header of two runs
  is identical and two exports are comparable.

Nothing here invents a value: an absent one stays absent (§24.3, §37).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.core.hashing import canonical_json

__all__ = ["cell_text", "default_columns"]


def cell_text(value: Any) -> str:
    """Return the tabular text of *value*, preserving nested structures."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    return canonical_json(value)


def default_columns(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return the sorted union of the row keys.

    Sorting (instead of first-seen order) is what makes the header of two runs
    over the same rows identical — a table whose columns move is not comparable.
    """
    columns: set[str] = set()
    for row in rows:
        columns.update(str(key) for key in row)
    return sorted(columns)
