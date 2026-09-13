"""Tests for CSV connector per §9.1."""

from pathlib import Path

import pytest

from app.connectors.base import Query
from app.connectors.files.csv_connector import CSVConnector


@pytest.mark.asyncio
async def test_csv_discover(tmp_path: Path) -> None:
    """Test CSV file discovery."""
    connector = CSVConnector(base_path=str(tmp_path))
    
    # Create test CSV file
    test_file = tmp_path / "test_data.csv"
    test_file.write_text("name,age\nAlice,30\nBob,25")
    
    query = Query(query_string="test")
    candidates = await connector.discover(query)
    
    assert len(candidates) == 1
    assert candidates[0].source_id == "csv-test_data"
    assert "test_data.csv" in candidates[0].location


@pytest.mark.asyncio
async def test_csv_retrieve(tmp_path: Path) -> None:
    """Test CSV data retrieval."""
    connector = CSVConnector(base_path=str(tmp_path))
    
    # Create test CSV file
    test_file = tmp_path / "test_data.csv"
    test_file.write_text("name,age\nAlice,30\nBob,25")
    
    query = Query(query_string="test")
    candidates = await connector.discover(query)
    raw = await connector.retrieve(candidates[0])
    
    assert raw.source_id == "csv-test_data"
    assert raw.content_type == "text/csv"
    assert "Alice" in raw.data


@pytest.mark.asyncio
async def test_csv_inspect(tmp_path: Path) -> None:
    """Test CSV metadata inspection."""
    connector = CSVConnector(base_path=str(tmp_path))
    
    # Create test CSV file
    test_file = tmp_path / "test_data.csv"
    test_file.write_text("name,age\nAlice,30\nBob,25")
    
    query = Query(query_string="test")
    candidates = await connector.discover(query)
    raw = await connector.retrieve(candidates[0])
    metadata = await connector.inspect(raw)
    
    assert metadata.source_id == "csv-test_data"
    assert metadata.record_count == 2
    assert metadata.schema == {"name": "string", "age": "string"}


@pytest.mark.asyncio
async def test_inspect_ignores_trailing_newline(tmp_path: Path) -> None:
    """Test that inspect ignores trailing newline in CSV."""
    connector = CSVConnector(base_path=str(tmp_path))
    
    # Create test CSV file with trailing newline
    test_file = tmp_path / "test_data.csv"
    test_file.write_text("name,age\nAlice,30\nBob,25\n")
    
    query = Query(query_string="test")
    candidates = await connector.discover(query)
    raw = await connector.retrieve(candidates[0])
    metadata = await connector.inspect(raw)
    
    assert metadata.record_count == 2


@pytest.mark.asyncio
async def test_inspect_ignores_blank_lines(tmp_path: Path) -> None:
    """Test that inspect ignores blank lines in CSV."""
    connector = CSVConnector(base_path=str(tmp_path))
    
    # Create test CSV file with blank lines
    test_file = tmp_path / "test_data.csv"
    test_file.write_text("name,age\nAlice,30\n\nBob,25\n")
    
    query = Query(query_string="test")
    candidates = await connector.discover(query)
    raw = await connector.retrieve(candidates[0])
    metadata = await connector.inspect(raw)
    
    assert metadata.record_count == 2
