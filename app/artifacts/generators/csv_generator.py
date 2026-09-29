"""CSV export of a requested dataset (§24.3 « données demandées »).

The file carries *data*, never a reformatted narrative: a nested cell keeps its
canonical JSON text, so nothing is dropped and nothing is invented (§37).

Two details are deliberate and documented:

* encoding is ``utf-8-sig`` — the BOM is what makes Excel open a UTF-8 CSV with
  its accents intact instead of mojibake;
* the default delimiter is ``;`` — the French Excel locale splits on the
  semicolon, so a comma-separated file opens as a single column there.

Both are parameters, not constants. Column order is the caller's when given,
otherwise the sorted union of the row keys, so two runs over the same data
export the same columns in the same order.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from typing import Any

from app.artifacts.generators.tabular import cell_text, default_columns
from app.core.errors import ValidationError

__all__ = ["DEFAULT_DELIMITER", "ENCODING", "default_columns", "generate_csv"]

#: The delimiter Excel expects in a French locale.
DEFAULT_DELIMITER = ";"

#: UTF-8 with BOM — required for Excel to detect the encoding.
ENCODING = "utf-8-sig"


def generate_csv(
    rows: Sequence[Mapping[str, Any]],
    *,
    columns: Sequence[str] | None = None,
    delimiter: str = DEFAULT_DELIMITER,
) -> bytes:
    """Return the CSV bytes of *rows* (§24.3).

    Args:
        rows: Tabular projection of the requested dataset.
        columns: Column order to use; defaults to :func:`default_columns`.
        delimiter: Field delimiter, ``;`` by default (see module docstring).

    Returns:
        The UTF-8 (BOM) encoded CSV document, CRLF line endings per RFC 4180.

    Raises:
        ValidationError: When no column can be determined: a file with no column
            would be delivered as if it carried data, which §24.3 forbids.
    """
    materialised: list[Mapping[str, Any]] = [dict(row) for row in rows]
    header = [str(column) for column in (columns if columns is not None else default_columns(materialised))]
    if not header:
        raise ValidationError(
            "generate_csv requires at least one column (§24.3): an export with no "
            "column carries no data and must not be delivered."
        )

    buffer = io.StringIO()
    writer = csv.writer(
        buffer,
        delimiter=delimiter,
        lineterminator="\r\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writerow(header)
    for row in materialised:
        writer.writerow([cell_text(row.get(column)) for column in header])
    return buffer.getvalue().encode(ENCODING)
