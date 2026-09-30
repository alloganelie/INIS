"""XML export of a §24 delivery payload (§24, format ``xml``).

The mapping is total and lossless: nested mappings become child elements,
sequences become repeated ``<item>`` elements (with a ``count`` attribute so a
truncated list is detectable), and a ``None`` value becomes an empty element
flagged ``nil="true"`` instead of an invented empty string (§37).

Element order is deterministic (mapping keys are written sorted), so the same
payload always produces the same document — which is what lets the §24.2
``sha256`` be recomputed by the client that received the file.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from lxml import etree

from app.core.errors import ValidationError

__all__ = ["ITEM_TAG", "ROOT_TAG", "generate_xml"]

#: Root element of a delivered XML file.
ROOT_TAG = "information_package"

#: Element used for every member of a sequence.
ITEM_TAG = "item"

#: Characters an XML element name cannot contain.
_INVALID_NAME_CHARS = re.compile(r"[^A-Za-z0-9_.\-]")


def _tag(name: str) -> str:
    """Return *name* as a valid, stable XML element name."""
    cleaned = _INVALID_NAME_CHARS.sub("_", str(name))
    if not cleaned:
        return "field"
    if not (cleaned[0].isalpha() or cleaned[0] == "_"):
        return f"field_{cleaned}"
    return cleaned


def _serialise(parent: etree._Element, key: str, value: Any) -> etree._Element:
    """Append the element for ``key: value`` under *parent* and return it."""
    element = etree.SubElement(parent, _tag(key))
    if isinstance(value, Mapping):
        for child_key in sorted(value, key=str):
            _serialise(element, str(child_key), value[child_key])
    elif isinstance(value, (list, tuple)):
        element.set("count", str(len(value)))
        for item in value:
            _serialise(element, ITEM_TAG, item)
    elif value is None:
        # §37 — the absence of a value is stated, never turned into text.
        element.set("nil", "true")
    elif isinstance(value, bool):
        element.text = "true" if value else "false"
    else:
        element.text = str(value)
    return element


def generate_xml(payload: Mapping[str, Any], *, root_tag: str = ROOT_TAG) -> bytes:
    """Return the XML bytes of *payload* (§24).

    Args:
        payload: The §24.1 delivery payload to serialise.
        root_tag: Name of the root element.

    Returns:
        A UTF-8 XML document with its declaration, indented for readability.

    Raises:
        ValidationError: When *payload* is not a mapping — an XML document has a
            single root, so a scalar or a list cannot carry a delivery.
    """
    if not isinstance(payload, Mapping):
        raise ValidationError(
            "generate_xml expects a mapping payload (§24): an XML delivery has a "
            "single root element describing the package."
        )
    root = etree.Element(_tag(root_tag))
    for key in sorted(payload, key=str):
        _serialise(root, str(key), payload[key])
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True)
