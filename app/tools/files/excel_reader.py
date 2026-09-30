"""``read_excel`` internal tool per §21.

Replaces the v1 ``excel_connector`` stub (§2.3): the first worksheet (or an
explicitly named one) is read with ``openpyxl``, the first non-empty row is the
header, and empty trailing rows are ignored. Formula cells yield their cached
value; a formula with no cached result stays ``None`` rather than being
recomputed with a guessed value (§1.2).
"""

from __future__ import annotations

from pathlib import Path

from app.core.errors import InfrastructureError, ValidationError
from app.domain.entities.dataset import Dataset
from app.tools.files.dataset_builder import build_dataset, normalize_rows

__all__ = ["DEFAULT_SHEET_INDEX", "list_sheets", "load_excel", "read_excel"]

#: Worksheet name used when the caller does not select one.
DEFAULT_SHEET_INDEX = 0


def list_sheets(path: str) -> list[str]:
    """Return the worksheet names of the workbook at *path*, in workbook order.

    The list is what lets a caller *name* the sheet it read — and the sheets it
    did not read — instead of presenting a multi-sheet workbook as if it had one
    worksheet (§0.2). Reading a workbook does not require analysing every cell,
    so this stays a cheap header read.

    Args:
        path: Path of the ``.xlsx``/``.xlsm`` file.

    Returns:
        One entry per worksheet, in the order the workbook declares them.

    Raises:
        ValidationError: If the file is missing.
        InfrastructureError: If ``openpyxl`` is unavailable or the workbook
            cannot be parsed.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise ValidationError(f"excel file not found: {path}")

    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - §4.1 pins openpyxl
        raise InfrastructureError("openpyxl is required to read Excel files") from exc

    try:
        workbook = openpyxl.load_workbook(str(file_path), read_only=True, data_only=True)
    except Exception as exc:
        raise InfrastructureError(f"could not open Excel workbook: {exc}") from exc
    try:
        return list(workbook.sheetnames)
    finally:
        workbook.close()


def load_excel(
    path: str,
    *,
    source_id: str,
    sheet_name: str | None = None,
    sheet_index: int = DEFAULT_SHEET_INDEX,
) -> tuple[Dataset, list[dict]]:
    """Parse the workbook at *path* and return its dataset together with its rows.

    Args:
        path: Path of the ``.xlsx``/``.xlsm`` file.
        source_id: Identifier of the source the file belongs to (§0.2).
        sheet_name: Optional worksheet name; takes precedence over *sheet_index*.
        sheet_index: Zero-based worksheet index used when *sheet_name* is ``None``.

    Returns:
        ``(dataset, rows)``.

    Raises:
        ValidationError: If the file or the requested worksheet is missing.
        InfrastructureError: If ``openpyxl`` is unavailable or the workbook
            cannot be parsed.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise ValidationError(f"excel file not found: {path}")

    try:
        import openpyxl
    except ImportError as exc:  # pragma: no cover - §4.1 pins openpyxl
        raise InfrastructureError("openpyxl is required to read Excel files") from exc

    try:
        workbook = openpyxl.load_workbook(
            str(file_path), read_only=True, data_only=True
        )
    except Exception as exc:
        raise InfrastructureError(f"could not open Excel workbook: {exc}") from exc

    try:
        if sheet_name is not None:
            if sheet_name not in workbook.sheetnames:
                raise ValidationError(f"worksheet '{sheet_name}' not found in {path}")
            worksheet = workbook[sheet_name]
        else:
            if sheet_index >= len(workbook.sheetnames):
                raise ValidationError(
                    f"sheet index {sheet_index} out of range ({len(workbook.sheetnames)} sheets)"
                )
            worksheet = workbook[workbook.sheetnames[sheet_index]]

        raw_rows = [
            [cell for cell in row]
            for row in worksheet.iter_rows(values_only=True)
        ]
    finally:
        workbook.close()

    payload = [row for row in raw_rows if any(value is not None for value in row)]
    if not payload:
        raise ValidationError(f"worksheet '{worksheet.title}' is empty")

    header = [str(value).strip() if value is not None else f"column_{index}"
              for index, value in enumerate(payload[0])]
    records = [
        {header[index] if index < len(header) else f"column_{index}": value
         for index, value in enumerate(row)}
        for row in payload[1:]
    ]

    rows = normalize_rows(records)
    return (
        build_dataset(rows, source_id=source_id, storage_ref=file_path.resolve().as_uri()),
        rows,
    )


def read_excel(
    path: str,
    *,
    source_id: str,
    sheet_name: str | None = None,
    sheet_index: int = DEFAULT_SHEET_INDEX,
) -> Dataset:
    """Return the §21 ``Dataset`` read from the workbook at *path*."""
    dataset, _rows = load_excel(
        path, source_id=source_id, sheet_name=sheet_name, sheet_index=sheet_index
    )
    return dataset
