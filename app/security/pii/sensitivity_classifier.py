"""Sensitivity classification per INIS §19.4."""

from typing import Any, Literal

from app.security.pii.pii_detector import PIIDetector


class SensitivityClassifier:
    """Classify data sensitivity based on PII and other factors."""

    def __init__(self, pii_detector: PIIDetector | None = None):
        """Initialize sensitivity classifier.

        Args:
            pii_detector: Optional PII detector (creates default if not provided)
        """
        self.pii_detector = pii_detector or PIIDetector()

    def classify(self, text: str, explicit_classification: str | None = None) -> dict[str, Any]:
        """Classify text sensitivity.

        Args:
            text: Text to classify
            explicit_classification: Optional explicit classification override

        Returns:
            Dictionary with sensitivity level, PII flag, and categories
        """
        if explicit_classification:
            if explicit_classification not in ["low", "medium", "high", "critical"]:
                raise ValueError("Invalid classification level")
            sensitivity = explicit_classification
        else:
            sensitivity = self._determine_sensitivity(text)

        pii_matches = self.pii_detector.detect(text)
        categories = list(set(match.category for match in pii_matches))

        return {
            "sensitivity": sensitivity,
            "pii": len(pii_matches) > 0,
            "categories": categories
        }

    def _determine_sensitivity(self, text: str) -> Literal["low", "medium", "high", "critical"]:
        """Determine sensitivity level based on PII content.

        Args:
            text: Text to analyze

        Returns:
            Sensitivity level
        """
        pii_matches = self.pii_detector.detect(text)

        if not pii_matches:
            return "low"

        categories = set(match.category for match in pii_matches)

        if "credit_card" in categories or "ssn" in categories or "iban" in categories:
            return "critical"

        if "email" in categories and "phone" in categories:
            return "high"

        if len(categories) >= 2:
            return "high"

        return "medium"
