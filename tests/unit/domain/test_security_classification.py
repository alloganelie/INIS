"""Tests for the SecurityClassification domain entity."""

import pytest
from pydantic import ValidationError

from app.domain.entities import SecurityClassification


def test_security_classification_accepts_pii_categories() -> None:
    """A PII-bearing classification preserves its sensitivity metadata."""
    classification = SecurityClassification(
        sensitivity="high", pii=True, categories=["email", "phone"]
    )

    assert classification.categories == ["email", "phone"]
    assert classification.pii is True


def test_security_classification_defaults_to_empty_categories() -> None:
    """A non-PII resource may have no PII category."""
    classification = SecurityClassification(sensitivity="low", pii=False)

    assert classification.categories == []


def test_security_classification_rejects_unknown_sensitivity() -> None:
    """Only §19.4 sensitivity values are accepted."""
    with pytest.raises(ValidationError):
        SecurityClassification(sensitivity="public", pii=False)
