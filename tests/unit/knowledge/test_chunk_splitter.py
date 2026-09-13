"""Tests for sentence-aware chunk splitting."""

import pytest

from app.knowledge.chunking.chunk_splitter import ChunkSplitter


def test_chunk_splitter_returns_empty_list_for_empty_text() -> None:
    assert ChunkSplitter().split("") == []


def test_chunk_splitter_bounds_chunks_and_retains_overlap() -> None:
    chunks = ChunkSplitter().split(
        "One two three. Four five six. Seven eight nine.", max_tokens=5, overlap=2
    )

    assert all(len(chunk.split()) <= 5 for chunk in chunks)
    assert chunks[0].split()[-2:] == chunks[1].split()[:2]


def test_chunk_splitter_rejects_invalid_limits() -> None:
    splitter = ChunkSplitter()

    with pytest.raises(ValueError):
        splitter.split("Text.", max_tokens=0)
    with pytest.raises(ValueError):
        splitter.split("Text.", max_tokens=3, overlap=3)
