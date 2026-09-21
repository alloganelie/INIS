"""Source reliability scoring based on domain patterns per §10.2."""

import re
from typing import Any


class SourceReliabilityScorer:
    """Score source reliability based on URL domain patterns.

    Implements the reliability hierarchy defined in INIS §10.2:
    1. Government sources → 0.95
    2. Public institutions → 0.9
    3. Scientific articles → 0.9
    4. International organizations → 0.9
    5. Companies → 0.7
    6. Media → 0.6
    7. Forums/social networks → 0.3
    """

    RULES: list[tuple[str, float, str]] = [
        # Government sources (most specific first)
        (r".*\.gouv\.fr$", 0.95, "government"),
        (r".*\.gouv\.[a-z]{2}$", 0.95, "government"),
        (r".*\.gov\.uk$", 0.95, "government"),
        (r".*\.gov$", 0.95, "government"),
        (r".*\.go\.[a-z]{2}$", 0.95, "government"),
        
        # Educational institutions
        (r".*\.ac\.uk$", 0.9, "academic"),
        (r".*\.ac\.[a-z]{2}$", 0.9, "academic"),
        (r".*\.edu$", 0.9, "academic"),
        
        # Wikipedia (slightly lower than academic)
        (r"wikipedia\.org$", 0.85, "encyclopedia"),
        
        # International organizations
        (r"who\.int$", 0.9, "international"),
        (r"un\.org$", 0.9, "international"),
        (r"worldbank\.org$", 0.9, "international"),
        (r"oecd\.org$", 0.9, "international"),
        (r"imf\.org$", 0.9, "international"),
        
        # Scientific publications
        (r"nature\.com$", 0.9, "scientific"),
        (r"science\.org$", 0.9, "scientific"),
        (r"arxiv\.org$", 0.9, "scientific"),
        (r"springer\.com$", 0.9, "scientific"),
        (r"sciencedirect\.com$", 0.9, "scientific"),
        (r"ieee\.org$", 0.9, "scientific"),
        
        # Social media and forums (lowest reliability - must come before general .com)
        (r"twitter\.com$", 0.3, "social_media"),
        (r"x\.com$", 0.3, "social_media"),
        (r"facebook\.com$", 0.3, "social_media"),
        (r"reddit\.com$", 0.3, "social_media"),
        (r"linkedin\.com$", 0.3, "social_media"),
        (r"instagram\.com$", 0.3, "social_media"),
        (r"tiktok\.com$", 0.3, "social_media"),
        (r"youtube\.com$", 0.3, "social_media"),
        
        # Media (lower reliability - must come before general .com)
        (r"reuters\.com$", 0.6, "media"),
        (r"lemonde\.fr$", 0.6, "media"),
        (r"bbc\.com$", 0.6, "media"),
        (r"nytimes\.com$", 0.6, "media"),
        (r"theguardian\.com$", 0.6, "media"),
        (r"cnn\.com$", 0.6, "media"),
        
        # Companies (medium reliability - most general)
        (r".*\.com$", 0.7, "company"),
        (r".*\.net$", 0.7, "company"),
        (r".*\.co\.[a-z]{2}$", 0.7, "company"),
    ]

    def __init__(self) -> None:
        """Initialize the scorer with compiled regex patterns."""
        self._compiled_rules = [
            (re.compile(pattern), score, category)
            for pattern, score, category in self.RULES
        ]

    def score(self, url: str) -> float:
        """Return a reliability score (0-1) based on the URL domain.

        Args:
            url: The URL to score.

        Returns:
            Reliability score between 0 and 1.
            Returns 0.5 (neutral) if no rule matches.
        """
        if not url:
            return 0.5

        # Extract domain from URL
        domain = self._extract_domain(url)
        if not domain:
            return 0.5

        # Match against rules in order (first match wins)
        for pattern, score, _ in self._compiled_rules:
            if pattern.search(domain):
                return score

        # Default neutral score for unknown domains
        return 0.5

    def explain(self, url: str) -> dict[str, Any]:
        """Return detailed explanation of the reliability scoring.

        Args:
            url: The URL to analyze.

        Returns:
            Dictionary with url, score, category, and reason.
        """
        if not url:
            return {
                "url": url,
                "score": 0.5,
                "category": "unknown",
                "reason": "Empty URL provided",
            }

        domain = self._extract_domain(url)
        if not domain:
            return {
                "url": url,
                "score": 0.5,
                "category": "unknown",
                "reason": "Could not extract domain from URL",
            }

        # Find matching rule
        for pattern, score, category in self._compiled_rules:
            if pattern.search(domain):
                return {
                    "url": url,
                    "domain": domain,
                    "score": score,
                    "category": category,
                    "reason": f"Domain matches {category} pattern: {pattern.pattern}",
                }

        # No match found
        return {
            "url": url,
            "domain": domain,
            "score": 0.5,
            "category": "unknown",
            "reason": "Domain does not match any known reliability pattern",
        }

    def _extract_domain(self, url: str) -> str | None:
        """Extract the domain from a URL.

        Args:
            url: The URL to extract domain from.

        Returns:
            The domain part of the URL, or None if invalid.
        """
        try:
            # Remove protocol
            if "://" in url:
                url = url.split("://", 1)[1]
            
            # Remove path and query
            if "/" in url:
                url = url.split("/", 1)[0]
            if "?" in url:
                url = url.split("?", 1)[0]
            if "#" in url:
                url = url.split("#", 1)[0]
            
            # Remove port
            if ":" in url:
                url = url.split(":", 1)[0]
            
            return url.lower()
        except Exception:
            return None
