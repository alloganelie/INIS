"""``read_xml`` internal tool per §21.

Records are the repeated children of the root element (or of *record_path* when
supplied). Attributes are included as columns prefixed with ``@``; nested
elements are kept as ``json`` values instead of being flattened (§0.2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lxml import etree

from app.core.errors import InfrastructureError, ValidationError
from app.domain.entities.dataset import Dataset
from app.tools.files.dataset_builder import build_dataset, normalize_rows

__all__ = ["read_xml", "load_xml"]


def _element_to_record(element: etree._Element) -> dict[str, Any]:
    """Convert one XML element into a flat mapping of its own content."""
    record: dict[str, Any] = {}
    for name, value in element.attrib.items():
        record[f"@{name}"] = value

    children = list(element)
    for child in children:
        key = child.tag
        if len(child) == 0 and not child.attrib:
            record[key] = child.text
            continue
        record[key] = {name: value for name, value in child.attrib.items()}
        record[key]["#text"] = child.text

    if not children and element.text and element.text.strip():
        record["#text"] = element.text.strip()
    return record


def load_xml(
    path: str,
    *,
    source_id: str,
    record_path: str | None = None,
) -> tuple[Dataset, list[dict]]:
    """Parse the XML file at *path* and return its dataset together with its rows.

    Args:
        path: Path of the XML file.
        source_id: Identifier of the source the file belongs to (§0.2).
        record_path: Optional XPath selecting the repeated record elements.

    Returns:
        ``(dataset, rows)``.

    Raises:
        ValidationError: If the file is missing or *record_path* selects nothing.
        InfrastructureError: If the payload is not well-formed XML.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise ValidationError(f"xml file not found: {path}")

    try:
        tree = etree.parse(str(file_path))
    except etree.XMLSyntaxError as exc:
        raise InfrastructureError(f"invalid XML payload: {exc}") from exc

    root = tree.getroot()
    if record_path:
        # ``xpath`` may select attributes or text nodes; keep only real elements
        # so a mistyped path fails loudly instead of degrading every row to a scalar.
        selected = [
            node for node in root.xpath(record_path) if isinstance(node, etree._Element)
        ]
        if not selected:
            raise ValidationError(f"record_path '{record_path}' selected no element")
        elements = [node for node in selected if node is not root] or selected
    else:
        elements = list(root) or [root]

    rows = normalize_rows([_element_to_record(element) for element in elements])
    return (
        build_dataset(rows, source_id=source_id, storage_ref=file_path.resolve().as_uri()),
        rows,
    )


def read_xml(path: str, *, source_id: str, record_path: str | None = None) -> Dataset:
    """Return the §21 ``Dataset`` read from the XML file at *path*."""
    dataset, _rows = load_xml(path, source_id=source_id, record_path=record_path)
    return dataset
