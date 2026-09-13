"""Tests for search implementations per §16."""

import pytest

from app.storage.search.fulltext_search import FullTextSearch
from app.storage.search.hybrid_search import HybridSearch
from app.storage.search.vector_search import VectorSearch


@pytest.mark.asyncio
async def test_vector_search() -> None:
    """Test vector search initialization."""
    search = VectorSearch(connection_string="postgresql://test")
    assert search._connection_string == "postgresql://test"
    
    # Stub returns empty list
    results = await search.search(
        owner_type="information_unit",
        query_vector=[0.1] * 1536,
        limit=10,
    )
    assert results == []


@pytest.mark.asyncio
async def test_hybrid_search() -> None:
    """Test hybrid search initialization."""
    search = HybridSearch(connection_string="postgresql://test")
    assert search._connection_string == "postgresql://test"
    
    # Stub returns empty list
    results = await search.search(
        query="test query",
        query_vector=[0.1] * 1536,
        limit=10,
    )
    assert results == []


@pytest.mark.asyncio
async def test_fulltext_search() -> None:
    """Test full-text search initialization."""
    search = FullTextSearch(connection_string="postgresql://test")
    assert search._connection_string == "postgresql://test"
    
    # Stub returns empty list
    results = await search.search(
        query="test query",
        limit=10,
    )
    assert results == []
