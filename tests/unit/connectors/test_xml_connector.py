"""Tests for XMLConnector per §9.1 (tmp_path, no network)."""

from pathlib import Path

import pytest

from app.connectors.base import Query
from app.connectors.files.xml_connector import XMLConnector

XML_DOC = """<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns:bk="http://example.com/book">
  <bk:book><bk:title>Python 101</bk:title></bk:book>
  <bk:book><bk:title>XML Guide</bk:title></bk:book>
</catalog>
"""


@pytest.mark.asyncio
async def test_xml_discover(tmp_path: Path) -> None:
    """XML files matching the query are discovered."""
    (tmp_path / "catalog_test.xml").write_text(XML_DOC, encoding="utf-8")
    (tmp_path / "other.xml").write_text("<root/>", encoding="utf-8")

    candidates = await XMLConnector(base_path=str(tmp_path)).discover(
        Query(query_string="catalog")
    )

    assert len(candidates) == 1
    assert candidates[0].source_id == "xml-catalog_test"


@pytest.mark.asyncio
async def test_xml_retrieve(tmp_path: Path) -> None:
    """Raw XML content is retrieved with the XML content type."""
    (tmp_path / "catalog_test.xml").write_text(XML_DOC, encoding="utf-8")
    connector = XMLConnector(base_path=str(tmp_path))

    candidates = await connector.discover(Query(query_string="catalog"))
    raw = await connector.retrieve(candidates[0])

    assert raw.content_type == "application/xml"
    assert "Python 101" in raw.data


@pytest.mark.asyncio
async def test_xml_inspect(tmp_path: Path) -> None:
    """Inspect reports root tag, record count and namespaces."""
    (tmp_path / "catalog_test.xml").write_text(XML_DOC, encoding="utf-8")
    connector = XMLConnector(base_path=str(tmp_path))

    candidates = await connector.discover(Query(query_string="catalog"))
    raw = await connector.retrieve(candidates[0])
    metadata = await connector.inspect(raw)

    assert metadata.record_count == 2
    assert metadata.schema is not None
    assert metadata.schema["root"] == "catalog"
    assert "book" in metadata.schema["child_tags"]
    assert "http://example.com/book" in metadata.schema["namespaces"]
