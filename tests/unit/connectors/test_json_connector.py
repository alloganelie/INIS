"""Tests for JSON connector per §9.1."""

from pathlib import Path

import pytest

from app.connectors.base import Query
from app.connectors.files.json_connector import JSONConnector


@pytest.mark.asyncio
async def test_json_discover(tmp_path: Path) -> None:
    """Test JSON file discovery."""
    connector = JSONConnector(base_path=str(tmp_path))
    
    # Create test JSON file
    test_file = tmp_path / "test_data.json"
    test_file.write_text('{"name": "Alice", "age": 30}')
    
    query = Query(query_string="test")
    candidates = await connector.discover(query)
    
    assert len(candidates) == 1
    assert candidates[0].source_id == "json-test_data"
    assert "test_data.json" in candidates[0].location


@pytest.mark.asyncio
async def test_json_retrieve(tmp_path: Path) -> None:
    """Test JSON data retrieval."""
    connector = JSONConnector(base_path=str(tmp_path))
    
    # Create test JSON file
    test_file = tmp_path / "test_data.json"
    test_file.write_text('{"name": "Alice", "age": 30}')
    
    query = Query(query_string="test")
    candidates = await connector.discover(query)
    raw = await connector.retrieve(candidates[0])
    
    assert raw.source_id == "json-test_data"
    assert raw.content_type == "application/json"
    assert "Alice" in raw.data


@pytest.mark.asyncio
async def test_json_inspect(tmp_path: Path) -> None:
    """Test JSON metadata inspection."""
    connector = JSONConnector(base_path=str(tmp_path))
    
    # Create test JSON file
    test_file = tmp_path / "test_data.json"
    test_file.write_text('{"name": "Alice", "age": 30}')
    
    query = Query(query_string="test")
    candidates = await connector.discover(query)
    raw = await connector.retrieve(candidates[0])
    metadata = await connector.inspect(raw)
    
    assert metadata.source_id == "json-test_data"
    assert metadata.record_count == 1
    assert metadata.schema == {"name": "str", "age": "int"}
