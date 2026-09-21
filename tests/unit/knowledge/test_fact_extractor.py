"""Tests for source-backed fact extraction."""

import pytest

from app.domain.value_objects.ulid import ULID
from app.knowledge.extraction import FactExtractor, split_sentences


SOURCE_ID = "SRC_01H00000000000000000000000"
DOCUMENT_ID = "DOC_01H00000000000000000000000"
URL = "https://example.test/report"
TEXT = (
    "INIS retains complete provenance for every extracted factual statement. "
    "The system keeps each raw source sentence available for review."
)


async def test_extract_produces_valid_information_units() -> None:
    """Extracted payloads retain all required §11 fields and provenance."""
    facts = await FactExtractor().extract(TEXT, SOURCE_ID, DOCUMENT_ID, URL)

    assert len(facts) == 2
    for fact in facts:
        assert ULID.is_valid(fact["information_id"])
        assert fact["type"] == "text"
        assert fact["content"]["text"]
        assert fact["source_id"] == SOURCE_ID
        assert fact["document_id"] == DOCUMENT_ID
        assert fact["data_stage"] == "raw"
        assert fact["epistemic_status"] == "factual"
        assert fact["provenance"] == {
            "extracted_from": URL,
            "method": "fact_extractor",
        }


async def test_extract_requires_source_id() -> None:
    """Factual extraction rejects a missing source identifier."""
    with pytest.raises(ValueError, match="source_id"):
        await FactExtractor().extract(TEXT, "", DOCUMENT_ID, URL)


async def test_extract_requires_document_id() -> None:
    """Factual extraction rejects a missing document identifier."""
    with pytest.raises(ValueError, match="document_id"):
        await FactExtractor().extract(TEXT, SOURCE_ID, "", URL)


async def test_each_fact_has_evidence_id() -> None:
    """Every extracted factual unit receives a valid evidence identifier."""
    facts = await FactExtractor().extract(TEXT, SOURCE_ID, DOCUMENT_ID, URL)

    assert all(ULID.is_valid(fact["evidence_id"]) for fact in facts)


def test_split_sentences_basic() -> None:
    """Sentence splitting uses terminal punctuation and ignores short noise."""
    text = "Brief. This sentence is long enough to retain! Another useful sentence follows?"

    assert split_sentences(text) == [
        "This sentence is long enough to retain!",
        "Another useful sentence follows?",
    ]
