"""Unit tests for §13.2 completeness scoring.

``CompletenessCheck`` scores the ratio of present, non-empty fields and lists
the missing ones so the pipeline can degrade the confidence score.
"""

from __future__ import annotations

import pytest

from app.quality.checks.completeness_check import CompletenessCheck


@pytest.fixture
def check() -> CompletenessCheck:
    """Return the stateless check under test."""
    return CompletenessCheck()


class TestScoring:
    """§13.2 — score == present fields / required fields."""

    async def test_all_fields_present(self, check: CompletenessCheck) -> None:
        """A fully populated record scores 1.0 with no issue."""
        result = await check.run({"title": "Paris", "url": "https://example.com"})
        assert result["score"] == 1.0
        assert result["issues"] == []
        assert result["details"]["required_fields"] == ["title", "url"]

    async def test_partially_populated_record(self, check: CompletenessCheck) -> None:
        """One empty field out of two halves the score and is reported."""
        result = await check.run({"title": "Paris", "url": ""})
        assert result["score"] == 0.5
        assert result["issues"] == ["url"]

    async def test_explicit_required_fields(self, check: CompletenessCheck) -> None:
        """``required_fields`` restricts the checklist to the named fields."""
        result = await check.run({"required_fields": ["a", "b", "c"], "a": 1, "b": 2, "c": 3})
        assert result["score"] == 1.0
        assert result["details"]["required_fields"] == ["a", "b", "c"]

    async def test_missing_key_is_reported(self, check: CompletenessCheck) -> None:
        """An absent key is missing even when other keys exist."""
        result = await check.run({"required_fields": ["a", "b"], "a": "x"})
        assert result["score"] == 0.5
        assert result["issues"] == ["b"]

    async def test_empty_required_list_scores_one(self, check: CompletenessCheck) -> None:
        """No required field means nothing can be missing (no division by zero)."""
        result = await check.run({"required_fields": []})
        assert result["score"] == 1.0
        assert result["issues"] == []


class TestFalsyValues:
    """§13.2 — ``0`` and ``False`` are values, not missing fields."""

    @pytest.mark.parametrize("value", [0, False, 0.0])
    async def test_falsy_scalars_count_as_present(
        self, check: CompletenessCheck, value: object
    ) -> None:
        """A legitimate zero/False is not an empty field."""
        result = await check.run({"required_fields": ["total"], "total": value})
        assert result["score"] == 1.0
        assert result["issues"] == []

    @pytest.mark.parametrize("value", [None, "", [], {}])
    async def test_empty_containers_and_none_are_missing(
        self, check: CompletenessCheck, value: object
    ) -> None:
        """``None``, empty strings, empty lists and empty dicts are missing."""
        result = await check.run({"required_fields": ["total"], "total": value})
        assert result["score"] == 0.0
        assert result["issues"] == ["total"]


class TestInputNormalization:
    """§13 — dicts, Pydantic models and unsupported targets."""

    async def test_pydantic_model_input(self, check: CompletenessCheck) -> None:
        """A Pydantic model is scored through ``model_dump``."""
        from pydantic import BaseModel

        class Target(BaseModel):
            title: str
            url: str

        result = await check.run(Target(title="Paris", url=""))
        assert result["score"] == 0.5
        assert result["details"]["required_fields"] == ["title", "url"]

    async def test_unsupported_target_is_fully_missing(
        self, check: CompletenessCheck
    ) -> None:
        """An unsupported target yields an empty mapping, hence score 1.0 (no fields)."""
        result = await check.run(object())
        assert result["score"] == 1.0
        assert result["details"]["required_fields"] == []

