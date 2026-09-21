"""Wikipedia page extractor (§9.1: pages Web).

Fetches a Wikipedia page over ``httpx`` and delegates text extraction to
``TrafilaturaExtractor`` (no duplicated extraction logic). Like the other
extractors, it never raises on fetch/extraction failure: it returns the
contract dict with an ``error`` message instead, so extraction can never
crash a collection pipeline. Only invalid argument types raise
``ValueError``.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.connectors.web.extractors.trafilatura_extractor import TrafilaturaExtractor

_USER_AGENT = "INIS/0.1 (research pipeline; contact: inis-local)"
_LANGUAGE_RE = re.compile(r"https?://([a-z-]{2,12})\.wikipedia\.org/", re.IGNORECASE)


def _detect_language(url: str) -> str | None:
    """Detect the Wikipedia language subdomain (``fr`` from fr.wikipedia.org)."""
    match = _LANGUAGE_RE.match(url)
    return match.group(1).lower() if match else None


class WikipediaExtractor:
    """Extract ``{title, text, language, url}`` from a Wikipedia page."""

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds
        self._text_extractor = TrafilaturaExtractor()

    async def extract(
        self,
        url: str,
        client: httpx.AsyncClient | None = None,
    ) -> dict[str, Any]:
        """Fetch ``url`` and extract its main text with trafilatura.

        Args:
            url: Wikipedia page URL.
            client: Optional injected ``httpx.AsyncClient`` (tests).

        Returns:
            Dict with ``title``, ``text``, ``language``, ``url`` and
            ``error`` (None on success, message on fetch failure).
        """
        if not isinstance(url, str) or not url:
            raise ValueError("url must be a non-empty string")
        language = _detect_language(url)
        try:
            http_client = client or self._client or httpx.AsyncClient(
                timeout=self._timeout_seconds
            )
            response = await http_client.get(url, headers={"User-Agent": _USER_AGENT})
            response.raise_for_status()
            html = response.text
        except Exception as exc:
            return {
                "title": None,
                "text": "",
                "language": language,
                "url": url,
                "error": f"wikipedia fetch failed: {exc}",
            }
        extracted = await self._text_extractor.extract(html, url)
        return {
            "title": extracted.get("title"),
            "text": extracted.get("text", ""),
            "language": language,
            "url": url,
            "error": extracted.get("error"),
        }
