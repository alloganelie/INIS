"""Tests for the SearchResult domain entity."""

import pytest
from pydantic import ValidationError

from app.domain.entities.search_result import SearchResult
from app.domain.entities.source_candidate import SourceCandidate


def test_search_result_valid_creation_uses_optional_defaults() -> None:
    result = SearchResult(
        title="INIS documentation",
        url="https://example.org/inis",
        score=0.8,
        provider="web_search",
    )

    assert result.snippet is None
    assert result.source_candidate is None


def test_search_result_accepts_source_candidate_and_validates_score() -> None:
    candidate = SourceCandidate(
        url="https://example.org/inis",
        provider="web_search",
        score=0.8,
    )
    result = SearchResult(
        title="INIS documentation",
        url="https://example.org/inis",
        snippet="Search result excerpt",
        score=0.9,
        provider="web_search",
        source_candidate=candidate,
    )

    assert result.source_candidate is candidate

    with pytest.raises(ValidationError):
        SearchResult(
            title="Invalid result",
            url="https://example.org/invalid",
            score=1.1,
            provider="web_search",
        )
