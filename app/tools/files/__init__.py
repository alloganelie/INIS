"""File, dataset and source tools per §21.

Public surface (the §21 names):

* readers — :func:`read_csv`, :func:`read_excel`, :func:`read_json`,
  :func:`read_xml`, :func:`read_pdf`, :func:`extract_document`
* dataset analysis — :func:`inspect_schema`, :func:`profile_dataset`,
  :func:`detect_duplicates`, :func:`validate_schema`
* quality — :func:`check_missing_values`, :func:`check_consistency`,
  :func:`check_freshness`
* cross-checking — :func:`compare_sources`

Each reader also exposes a ``load_*``/``*_text`` companion returning the
payload rows or the extracted text next to the §21 entity type.
"""

from app.tools.files.csv_reader import load_csv, read_csv
from app.tools.files.dataset_builder import build_dataset, infer_schema, normalize_rows
from app.tools.files.dataset_inspector import (
    check_consistency,
    check_missing_values,
    detect_duplicates,
    inspect_schema,
    profile_dataset,
    validate_schema,
)
from app.tools.files.document_reader import (
    build_document,
    extract_document,
    extract_document_text,
)
from app.tools.files.excel_reader import load_excel, read_excel
from app.tools.files.json_reader import load_json, read_json
from app.tools.files.pdf_reader import read_pdf, read_pdf_tables, read_pdf_text
from app.tools.files.source_comparator import check_freshness, compare_sources
from app.tools.files.xml_reader import load_xml, read_xml

__all__ = [
    "build_dataset",
    "build_document",
    "check_consistency",
    "check_freshness",
    "check_missing_values",
    "compare_sources",
    "detect_duplicates",
    "extract_document",
    "extract_document_text",
    "infer_schema",
    "inspect_schema",
    "load_csv",
    "load_excel",
    "load_json",
    "load_xml",
    "normalize_rows",
    "profile_dataset",
    "read_csv",
    "read_excel",
    "read_json",
    "read_pdf",
    "read_pdf_tables",
    "read_pdf_text",
    "read_xml",
    "validate_schema",
]
