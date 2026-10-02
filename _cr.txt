"""``read_csv`` internal tool per §21.

``read_csv(path)`` returns the §21 :class:`Dataset` type. Because the ``Dataset``
domain entity only carries the schema and the storage reference (§27), the
parsed rows are exposed through :func:`load_csv`, which returns both objects in
one pass. ``read_csv`` is the thin §21 façade over it.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

from app.core.errors import ValidationError
from app.domain.entities.dataset import Dataset
from app.tools.files.dataset_builder import build_dataset, normalize_rows

__all__ = ["read_csv", "load_csv"]


def _local_ref(path: Path) -> str:
    """Return the ``file://`` storage reference for a local path."""
    return path.resolve().as_uri()


def load_csv(
    path: str,
    *,
    source_id: str,
    delimiter: str | None = None,
    encoding: str = "utf-8-sig",
) -> tuple[Dataset, list[dict]]:
    """Parse *path* and return its dataset together with its rows.

    Args:
        path: Path of the CSV file.
        source_id: Identifier of the source the file belongs to (§0.2).
        delimiter: Optional explicit delimiter; when ``None`` the dialect is
            sniffed from the payload with the stdlib sniffer.
        encoding: Text encoding; ``utf-8-sig`` transparently drops a BOM.

    Returns:
        ``(dataset, rows)`` where rows are mappings keyed by header.

    Raises:
        ValidationError: If the file does not exist or has no header row.
        InfrastructureError: If the payload cannot be decoded or parsed.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise ValidationError(f"csv file not found: {path}")

    text = file_path.read_text(encoding=encoding)
    if delimiter is None:
        sample = text[:8192]
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","

    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValidationError(f"csv file has no header row: {path}")

    rows = normalize_rows(
        [{key: value for key, value in row.items()} for row in reader]
    )
    return (
        build_dataset(rows, source_id=source_id, storage_ref=_local_ref(file_path)),
        rows,
    )


def read_csv(path: str, *, source_id: str, delimiter: str | None = None) -> Dataset:
    """Return the §21 ``Dataset`` read from the CSV file at *path*."""
    dataset, _rows = load_csv(path, source_id=source_id, delimiter=delimiter)
    return dataset
