"""PII redaction per INIS §19.4."""

from typing import List

from app.security.pii.pii_detector import PIIDetector, PIIMatch


class Redactor:
    """Redact PII from text by masking detected values."""

    def __init__(self, pii_detector: PIIDetector | None = None):
        """Initialize redactor.

        Args:
            pii_detector: Optional PII detector (creates default if not provided)
        """
        self.pii_detector = pii_detector or PIIDetector()

    def redact(self, text: str, mask_char: str = "*") -> str:
        """Redact PII from text.

        Args:
            text: Text to redact
            mask_char: Character to use for masking (default: *)

        Returns:
            Text with PII redacted
        """
        matches = self.pii_detector.detect(text)

        if not matches:
            return text

        redacted_text = text
        offset = 0

        for match in sorted(matches, key=lambda m: m.start):
            start = match.start + offset
            end = match.end + offset
            original = match.value
            masked = mask_char * len(original)

            redacted_text = redacted_text[:start] + masked + redacted_text[end:]
            offset += len(masked) - len(original)

        return redacted_text

    def redact_selective(self, text: str, categories: List[str], mask_char: str = "*") -> str:
        """Redact only specific PII categories.

        Args:
            text: Text to redact
            categories: List of PII categories to redact
            mask_char: Character to use for masking (default: *)

        Returns:
            Text with specified PII categories redacted
        """
        all_matches = self.pii_detector.detect(text)
        filtered_matches = [m for m in all_matches if m.category in categories]

        if not filtered_matches:
            return text

        redacted_text = text
        offset = 0

        for match in sorted(filtered_matches, key=lambda m: m.start):
            start = match.start + offset
            end = match.end + offset
            original = match.value
            masked = mask_char * len(original)

            redacted_text = redacted_text[:start] + masked + redacted_text[end:]
            offset += len(masked) - len(original)

        return redacted_text
