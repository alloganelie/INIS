"""Tests for the Source domain entity."""

import pytest
from pydantic import ValidationError

from app.domain.entities.source import Source


def make_source(**overrides: object) -> Source:
    values: dict[str, object] = {
        "source_id": "SRC_01H00000000000000000000000",
        "type": "web_page",
        "url": "https://example.org/source",
        "reliability_score": 0.9,
        "freshness": {"retrieved_at": "2026-09-13T00:00:00Z"},
    }
    values.update(overrides)
    return Source(**values)


def test_source_valid_creation() -> None:
    source = make_source()

    assert source.source_id == "SRC_01H00000000000000000000000"
    assert source.reliability_score == 0.9


def test_source_requires_provenance_identifier() -> None:
    with pytest.raises(ValidationError):
        Source(
            type="web_page",
            url="https://example.org/source",
            reliability_score=0.9,
            freshness={},
        )


def test_source_rejects_invalid_reliability_score() -> None:
    with pytest.raises(ValidationError):
        make_source(reliability_score=1.1)
