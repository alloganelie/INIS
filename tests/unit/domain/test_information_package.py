"""Tests for the InformationPackage domain entity."""

from datetime import UTC, datetime

import pytest

from app.core.errors import ValidationError
from app.domain.entities.information_package import InformationPackage


def make_package(**overrides: object) -> InformationPackage:
    values: dict[str, object] = {
        "package_id": "INF_01H00000000000000000000000",
        "request_id": "REQ_01H00000000000000000000000",
        "units": [{"information_id": "INF_01H00000000000000000000000"}],
        "confidence": {"score": 0.9},
        "provenance": {"source_id": "SRC_01H00000000000000000000000"},
        "created_at": datetime.now(UTC),
        "data_stage": "raw",
    }
    values.update(overrides)
    return InformationPackage(**values)


def test_information_package_requires_provenance() -> None:
    package = make_package(provenance={})

    with pytest.raises(ValidationError, match="InformationPackage requires provenance"):
        package.validate()


def test_information_package_valid_creation() -> None:
    package = make_package()

    package.validate()

    assert package.provenance["source_id"] == "SRC_01H00000000000000000000000"


@pytest.mark.parametrize("data_stage", ["raw", "normalized", "enriched", "derived"])
def test_data_stage_values(data_stage: str) -> None:
    package = make_package(data_stage=data_stage)

    assert package.data_stage == data_stage
