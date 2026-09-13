"""Tests for sentence-aware chunk splitting."""

from app.knowledge.chunking.chunk_splitter import ChunkSplitter


def test_chunk_splitter_preserves_sentences_and_whole_sentence_overlap() -> None:
    chunks = ChunkSplitter().split(
        "One two three. Four five six. Seven eight nine.", max_tokens=6, overlap=3
    )

    assert chunks == [
        "One two three. Four five six.",
        "Four five six. Seven eight nine.",
    ]


def test_chunk_splitter_truncates_a_very_long_sentence_with_marker() -> None:
    chunks = ChunkSplitter().split("One two three four five six seven.", max_tokens=4)

    assert chunks == ["One two three …"]


def test_chunk_splitter_returns_empty_list_for_empty_text() -> None:
    assert ChunkSplitter().split("") == []
