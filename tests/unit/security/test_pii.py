"""Tests for PII detection and redaction per INIS §19.4."""

import pytest

from app.security.pii import PIIDetector, Redactor, SensitivityClassifier


def test_pii_detector_email():
    """Test email detection."""
    detector = PIIDetector()
    text = "Contact me at john.doe@example.com for details."
    matches = detector.detect(text)

    assert len(matches) == 1
    assert matches[0].category == "email"
    assert "john.doe@example.com" in matches[0].value


def test_pii_detector_phone():
    """Test phone number detection."""
    detector = PIIDetector()
    text = "Call me at 555-123-4567 tomorrow."
    matches = detector.detect(text)

    assert len(matches) == 1
    assert matches[0].category == "phone"


def test_pii_detector_multiple_types():
    """Test detection of multiple PII types."""
    detector = PIIDetector()
    text = "Email: jane@example.com, Phone: 555-987-6543"
    matches = detector.detect(text)

    assert len(matches) == 2
    categories = {m.category for m in matches}
    assert "email" in categories
    assert "phone" in categories


def test_pii_detector_no_pii():
    """Test text without PII."""
    detector = PIIDetector()
    text = "This is a normal text without personal information."
    matches = detector.detect(text)

    assert len(matches) == 0


def test_redactor_masks_pii():
    """Test PII redaction."""
    detector = PIIDetector()
    redactor = Redactor(detector)
    text = "Contact john@example.com for help."
    redacted = redactor.redact(text)

    assert "john@example.com" not in redacted
    assert "****************" in redacted


def test_redactor_selective_categories():
    """Test selective redaction by category."""
    detector = PIIDetector()
    redactor = Redactor(detector)
    text = "Email: john@example.com, Phone: 555-123-4567"
    redacted = redactor.redact_selective(text, ["email"])

    assert "john@example.com" not in redacted
    assert "555-123-4567" in redacted


def test_sensitivity_classifier_low():
    """Test classification of low sensitivity text."""
    classifier = SensitivityClassifier()
    text = "This is public information."
    result = classifier.classify(text)

    assert result["sensitivity"] == "low"
    assert result["pii"] is False


def test_sensitivity_classifier_medium():
    """Test classification of medium sensitivity text."""
    classifier = SensitivityClassifier()
    text = "Contact me at test@example.com"
    result = classifier.classify(text)

    assert result["sensitivity"] == "medium"
    assert result["pii"] is True
    assert "email" in result["categories"]


def test_sensitivity_classifier_critical():
    """Test classification of critical sensitivity text."""
    classifier = SensitivityClassifier()
    text = "SSN: 123-45-6789"
    result = classifier.classify(text)

    assert result["sensitivity"] == "critical"
    assert result["pii"] is True
