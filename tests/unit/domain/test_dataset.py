"""Tests for the Dataset domain entity."""

import pytest
from pydantic import ValidationError

from app.domain.entities.dataset import Dataset


def make_dataset(**overrides: object) -> Dataset:
    values: dict[str, object] = {
        "dataset_id": "DATA_01H00000000000000000000000",
        "source_id": "SRC_01H00000000000000000000000",
        "dataset_schema": {"columns": [{"name": "country", "type": "string"}]},
        "row_count": 42,
        "storage_ref": "s3://inis/datasets/countries.csv",
    }
    values.update(overrides)
    return Dataset(**values)


def test_dataset_valid_creation() -> None:
    dataset = make_dataset()

    assert dataset.dataset_id == "DATA_01H00000000000000000000000"
    assert dataset.row_count == 42


def test_dataset_requires_source_provenance() -> None:
    with pytest.raises(ValidationError):
        Dataset(
            dataset_id="DATA_01H00000000000000000000000",
            dataset_schema={},
            row_count=0,
            storage_ref="s3://inis/datasets/empty.csv",
        )


def test_dataset_rejects_negative_row_count() -> None:
    with pytest.raises(ValidationError):
        make_dataset(row_count=-1)
