"""Unit tests for §19.4 PII detection.

``PIIDetector`` is the first half of the §19.4 pipeline (detect, then redact);
a miss here means a leak downstream, so each documented category is asserted
with the exact match offsets used by the redactor.
"""

from __future__ import annotations

import pytest

from app.security.pii.pii_detector import PIIDetector, PIIMatch


@pytest.fixture
def detector() -> PIIDetector:
    """Return the detector under test."""
    return PIIDetector()


class TestDetection:
    """§19.4 — the six documented categories are recognized."""

    @pytest.mark.parametrize(
        ("category", "text"),
        [
            ("email", "contact agent@example.com now"),
            ("phone", "call 555-123-4567 today"),
            ("ssn", "ssn 123-45-6789 on file"),
            ("ip_address", "host 192.168.1.10 answers"),
            ("iban", "IBAN FR7630006000011234567890189 valid"),
        ],
    )
    def test_category_is_detected(
        self, detector: PIIDetector, category: str, text: str
    ) -> None:
        """The expected category appears among the matches."""
        assert category in {match.category for match in detector.detect(text)}

    def test_credit_card_digits_are_detected(self, detector: PIIDetector) -> None:
        """A 16-digit card number is flagged as ``credit_card``."""
        matches = detector.detect("card 4111 1111 1111 1111 expires soon")
        assert any(match.category == "credit_card" for match in matches)

    def test_offsets_point_at_the_matched_value(self, detector: PIIDetector) -> None:
        """``text[start:end]`` is exactly ``value`` (redactor contract)."""
        text = "mail: agent@example.com."
        for match in detector.detect(text):
            assert text[match.start : match.end] == match.value

    def test_match_is_a_typed_dataclass(self, detector: PIIDetector) -> None:
        """Matches expose category/start/end/value."""
        match = detector.detect("agent@example.com")[0]
        assert isinstance(match, PIIMatch)
        assert (match.category, match.value) == ("email", "agent@example.com")


class TestNoDetection:
    """§19.4 — clean text must not be flagged (no false positive)."""

    @pytest.mark.parametrize(
        "text",
        [
            "Paris is the capital of France.",
            "The report was published in 2026.",
            "",
        ],
    )
    def test_clean_text_has_no_pii(self, detector: PIIDetector, text: str) -> None:
        """Ordinary text yields no match and ``has_pii`` is False."""
        assert detector.detect(text) == []
        assert detector.has_pii(text) is False

    def test_pii_free_text_with_has_pii_helper(self, detector: PIIDetector) -> None:
        """``has_pii`` mirrors ``detect`` on a multi-sentence paragraph."""
        text = "INIS collects public web pages and stores their provenance."
        assert detector.has_pii(text) is False


class TestHasPii:
    """§19.4 — ``has_pii`` is the boolean shortcut used by callers."""

    @pytest.mark.parametrize(
        "text",
        [
            "agent@example.com",
            "123-45-6789",
            "server 10.0.0.1 responded",
        ],
    )
    def test_has_pii_true(self, detector: PIIDetector, text: str) -> None:
        """Any detected match makes ``has_pii`` True."""
        assert detector.has_pii(text) is True

    def test_multiple_categories_in_one_text(self, detector: PIIDetector) -> None:
        """Several categories may be found in the same text."""
        text = "agent@example.com / 123-45-6789"
        categories = {match.category for match in detector.detect(text)}
        assert {"email", "ssn"} <= categories

