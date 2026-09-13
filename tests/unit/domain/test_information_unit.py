"""Tests for the InformationUnit domain entity."""

from datetime import UTC, datetime

import pytest

from app.core.errors import ValidationError
from app.domain.entities.information_unit import InformationUnit


def make_information_unit(**overrides: object) -> InformationUnit:
    values: dict[str, object] = {
        "information_id": "INF_01H00000000000000000000000",
        "type": "text",
        "content": {"value": "INIS is traceable."},
        "raw_reference": {"excerpt": "INIS is traceable."},
        "source_id": "SRC_01H00000000000000000000000",
        "document_id": "DOC_01H00000000000000000000000",
        "dataset_id": None,
        "location": {"page": 1},
        "context": {"section": "overview"},
        "language": "en",
        "unit": None,
        "time": {},
        "classification": {},
        "quality": {"score": 0.9},
        "confidence": {"score": 0.9},
        "provenance": {"source_id": "SRC_01H00000000000000000000000"},
        "versions": ["INF_01H00000000000000000000000"],
        "data_stage": "raw",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    values.update(overrides)
    return InformationUnit(**values)


def test_information_unit_valid_creation() -> None:
    unit = make_information_unit()

    unit.validate()
    assert unit.type == "text"


def test_information_unit_requires_provenance() -> None:
    unit = make_information_unit(provenance={})

    with pytest.raises(ValidationError, match="InformationUnit requires provenance"):
        unit.validate()


def test_information_unit_rejects_invalid_data_stage() -> None:
    with pytest.raises(Exception):
        make_information_unit(data_stage="unverified")
