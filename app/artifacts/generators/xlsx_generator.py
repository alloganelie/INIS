"""XLSX export of a §24 delivery (§24.3 « Export Excel »).

§24.3 lists the *possible* sheets of the workbook: the requested data, the
metadata, the data dictionary, the sources, the provenance, the quality
controls and the version. Each becomes a sheet, in that fixed order, so two
workbooks of the same delivery are comparable.

A sheet the delivery carries no data for is written with its header row and
nothing else, and the caller reports the gap in ``limitations`` (§37) — INIS
never fills a cell with a guessed value (§24.3 last line).

One caveat, stated rather than hidden: the bytes of an ``.xlsx`` are a ZIP
archive whose entries carry timestamps, so two generations of the same content
are not bit-identical. The ``sha256`` of the §24.2 record is therefore the
digest of the file that was actually delivered, which is exactly what §24.2
asks for; a test comparing two generations must compare their *content* (cells),
not their bytes.
"""

from __future__ import annotations

import io
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

from app.artifacts.generators.tabular import cell_text, default_columns

__all__ = ["SHEET_ORDER", "SHEET_TITLES", "generate_xlsx"]

#: Canonical sheet key → §24.3 sheet title (French, as the spec names them).
SHEET_TITLES: dict[str, str] = {
    "data": "données",
    "metadata": "métadonnées",
    "dictionary": "dictionnaire",
    "sources": "sources",
    "provenance": "provenance",
    "quality": "qualité",
    "version": "version",
}

#: The order the sheets appear in the workbook.
SHEET_ORDER: tuple[str, ...] = (
    "data",
    "metadata",
    "dictionary",
    "sources",
    "provenance",
    "quality",
    "version",
)

#: Character width used when a column has no obvious size.
DEFAULT_COLUMN_WIDTH = 24

#: A workbook claims no author: it is machine-generated and §37 forbids pretending otherwise.
CREATOR = "INIS"


def _columns(rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Return the sorted union of the row keys (deterministic header)."""
    return default_columns(rows)


def _write_sheet(
    workbook: Workbook,
    sheet_key: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    columns: Sequence[str] | None = None,
) -> None:
    """Write one §24.3 sheet: a bold header row, then the data rows."""
    sheet = workbook.create_sheet(SHEET_TITLES[sheet_key])
    header = [str(column) for column in (columns if columns is not None else _columns(rows))]
    if not header:
        # No column at all: the sheet exists and says so, rather than being
        # silently absent from a workbook a client asked for.
        sheet.append(["(aucune donnée)"])
        sheet.cell(row=1, column=1).font = Font(bold=True)
        sheet.column_dimensions["A"].width = DEFAULT_COLUMN_WIDTH
        return

    sheet.append(header)
    for index, column in enumerate(header, start=1):
        cell = sheet.cell(row=1, column=index)
        cell.font = Font(bold=True)
        sheet.column_dimensions[get_column_letter(index)].width = max(
            DEFAULT_COLUMN_WIDTH, len(column) + 4
        )
    for row in rows:
        sheet.append([cell_text(row.get(column)) for column in header])
    sheet.freeze_panes = "A2"


def generate_xlsx(
    sheets: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    *,
    columns: Sequence[str] | None = None,
) -> bytes:
    """Return the ``.xlsx`` bytes of a §24.3 workbook.

    Args:
        sheets: Mapping of sheet key (see :data:`SHEET_TITLES`) to its rows.
            Missing keys produce an empty sheet rather than no sheet.
        columns: Column order of the ``data`` sheet; the other sheets use the
            sorted union of their own keys.

    Returns:
        The workbook bytes.

    Raises:
        ValidationError: Never — an empty workbook is a legitimate delivery of
            "no data", and the gap is reported through ``limitations`` by the
            caller (the §24.3 contract has no "must contain data" clause).
    """
    materialised: dict[str, list[Mapping[str, Any]]] = {
        key: [dict(row) for row in (sheets or {}).get(key, [])] for key in SHEET_ORDER
    }

    workbook = Workbook()
    # ``Workbook()`` always creates one sheet; the first §24.3 sheet takes it.
    default_sheet = workbook.active
    workbook.remove(default_sheet)

    for sheet_key in SHEET_ORDER:
        _write_sheet(
            workbook,
            sheet_key,
            materialised[sheet_key],
            columns=columns if sheet_key == "data" else None,
        )

    workbook.properties.creator = CREATOR
    workbook.properties.lastModifiedBy = CREATOR
    # A fixed creation stamp keeps the workbook metadata stable across runs even
    # though the ZIP timestamps themselves are not (see the module docstring).
    workbook.properties.created = datetime(1970, 1, 1, tzinfo=UTC)

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
