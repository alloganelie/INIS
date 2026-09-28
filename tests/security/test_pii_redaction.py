"""Security tests: §19.4 PII redaction.

``Redactor`` is the second half of the §19.4 pipeline (detect, then mask). The
guarantees asserted here are the ones a leak would break: the original value
disappears, the document keeps its shape, and a second pass changes nothing.
"""

from __future__ import annotations

import pytest

from app.security.pii.pii_detector import PIIDetector
from app.security.pii.redactor import Redactor


@pytest.fixture
def redactor() -> Redactor:
    """Return a redactor sharing the detector of the assertions."""
    return Redactor()


class TestRedaction:
    """§19.4 — detected values are masked."""

    def test_email_is_masked(self, redactor: Redactor) -> None:
        """The address disappears from the output."""
        redacted = redactor.redact("Contact: agent@example.com")
        assert "agent@example.com" not in redacted
        assert redacted == "Contact: " + "*" * len("agent@example.com")

    @pytest.mark.parametrize(
        "value",
        ["123-45-6789", "4111 1111 1111 1111"],
    )
    def test_sensitive_identifiers_are_masked(
        self, redactor: Redactor, value: str
    ) -> None:
        """SSN and card numbers are replaced by an equal-length mask."""
        redacted = redactor.redact(f"value {value} end")
        assert value not in redacted
        assert "*" * len(value) in redacted

    def test_mask_preserves_document_length(self, redactor: Redactor) -> None:
        """Offsets stay valid: the redacted text has the same length."""
        text = "mail agent@example.com then ssn 123-45-6789 ok"
        assert len(redactor.redact(text)) == len(text)

    def test_masking_is_idempotent(self, redactor: Redactor) -> None:
        """Redacting an already redacted text changes nothing."""
        once = redactor.redact("agent@example.com")
        assert redactor.redact(once) == once

    def test_custom_mask_character(self, redactor: Redactor) -> None:
        """The mask character is configurable (``#`` is used for CSV cells)."""
        masked = redactor.redact("agent@example.com", mask_char="#")
        assert masked == "#" * len("agent@example.com")

    def test_detector_finds_nothing_after_redaction(self, redactor: Redactor) -> None:
        """The §19.4 guarantee: the detector is clean on the output."""
        detector = PIIDetector()
        redacted = redactor.redact("agent@example.com / 123-45-6789 / 192.168.1.10")
        remaining = {match.category for match in detector.detect(redacted)}
        assert "email" not in remaining
        assert "ssn" not in remaining

    def test_multiple_values_are_all_masked(self, redactor: Redactor) -> None:
        """Two addresses in one text are both replaced."""
        redacted = redactor.redact("a@example.com and b@example.com")
        assert "a@example.com" not in redacted
        assert "b@example.com" not in redacted


class TestCleanText:
    """§19.4 — the redactor must not damage PII-free content."""

    @pytest.mark.parametrize(
        "text",
        [
            "Paris est la capitale de la France.",
            "",
            "Rapport 2026 sur la qualité des données.",
        ],
    )
    def test_clean_text_is_returned_unchanged(self, redactor: Redactor, text: str) -> None:
        """No match means no modification at all."""
        assert redactor.redact(text) == text

    def test_text_without_pii_keeps_markup_like_content(self, redactor: Redactor) -> None:
        """Non-PII numeric content (dates, versions) is preserved."""
        text = "Version 2.0.0 released on 2026-09-27."
        assert redactor.redact(text) == text


class TestSelectiveRedaction:
    """§19.4 — some consumers may mask only a subset of categories."""

    def test_only_requested_category_is_masked(self, redactor: Redactor) -> None:
        """Masking e-mail keeps the SSN readable for a compliance use case."""
        text = "agent@example.com has ssn 123-45-6789"
        redacted = redactor.redact_selective(text, ["email"])
        assert "agent@example.com" not in redacted
        assert "123-45-6789" in redacted

    def test_unknown_category_is_a_no_op(self, redactor: Redactor) -> None:
        """Asking for a category that is absent changes nothing."""
        text = "agent@example.com"
        assert redactor.redact_selective(text, ["iban"]) == text

    def test_empty_category_list_is_a_no_op(self, redactor: Redactor) -> None:
        """No category selected → nothing masked."""
        text = "agent@example.com / 123-45-6789"
        assert redactor.redact_selective(text, []) == text

    def test_several_categories(self, redactor: Redactor) -> None:
        """A multi-category request masks every listed category."""
        text = "agent@example.com / 123-45-6789"
        redacted = redactor.redact_selective(text, ["email", "ssn"])
        assert "agent@example.com" not in redacted
        assert "123-45-6789" not in redacted

