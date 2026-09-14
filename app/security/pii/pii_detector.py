"""PII detection per INIS §19.4."""

import re
from dataclasses import dataclass
from typing import List


@dataclass
class PIIMatch:
    """Match of PII in text."""

    category: str
    start: int
    end: int
    value: str


class PIIDetector:
    """Detect Personally Identifiable Information in text."""

    def __init__(self):
        """Initialize PII detector with regex patterns."""
        self.patterns = {
            "email": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
            "phone": re.compile(r'\b(?:\+?(\d{1,3})?[-. ]?)?\(?\d{3}\)?[-. ]?\d{3}[-. ]?\d{4}\b'),
            "iban": re.compile(r'\b[A-Z]{2}[0-9]{2}[A-Z0-9]{4}[0-9]{7}([A-Z0-9]?){0,16}\b'),
            "credit_card": re.compile(r'\b(?:\d[ -]*?){13,16}\b'),
            "ssn": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
            "ip_address": re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'),
        }

    def detect(self, text: str) -> List[PIIMatch]:
        """Detect PII in text.

        Args:
            text: Text to scan for PII

        Returns:
            List of PII matches found
        """
        matches = []

        for category, pattern in self.patterns.items():
            for match in pattern.finditer(text):
                pii_match = PIIMatch(
                    category=category,
                    start=match.start(),
                    end=match.end(),
                    value=match.group()
                )
                matches.append(pii_match)

        return matches

    def has_pii(self, text: str) -> bool:
        """Check if text contains any PII.

        Args:
            text: Text to check

        Returns:
            True if PII is found, False otherwise
        """
        return len(self.detect(text)) > 0
