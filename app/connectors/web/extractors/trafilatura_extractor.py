"""Article-text extractor over trafilatura (§9.1: pages Web).

``trafilatura`` is imported lazily inside :meth:`TrafilaturaExtractor.extract`
so this module stays importable where the optional dependency is missing
(it is currently absent from ``pyproject.toml`` — see final report). When
trafilatura is unavailable or extraction fails, a graceful fallback returns
the contract dict with empty fields and an ``error`` message instead of
raising: extraction must never crash a collection pipeline.
"""

from __future__ import annotations

import re
from typing import Any

_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<[^>]+>")


def _fallback_title(html: str) -> str | None:
    """Extract a ``<title>`` with stdlib regex (no dependency)."""
    match = _TITLE_RE.search(html)
    if not match:
        return None
    title = _TAG_RE.sub("", match.group(1)).strip()
    return title or None


class TrafilaturaExtractor:
    """Extract main article text and metadata from raw HTML."""

    async def extract(self, html: str, url: str) -> dict[str, Any]:
        """Extract ``{title, text, author, date, language}`` (+ url, error).

        Never raises on extraction failure: returns empty fields with
        ``error`` set. Raises ``ValueError`` only on invalid input.
        """
        if not html or not isinstance(html, str):
            raise ValueError("html must be a non-empty string")
        if not url or not isinstance(url, str):
            raise ValueError("url must be a non-empty string")
        try:
            import trafilatura

            text = trafilatura.extract(html, include_comments=False, include_tables=True)
            result: dict[str, Any] = {
                "title": None,
                "text": text or "",
                "author": None,
                "date": None,
                "language": None,
                "url": url,
                "error": None,
            }
            try:
                metadata = trafilatura.extract_metadata(html)
            except Exception:
                metadata = None
            if metadata is not None:
                result["title"] = getattr(metadata, "title", None)
                result["author"] = getattr(metadata, "author", None)
                result["date"] = getattr(metadata, "date", None)
            if not result["title"]:
                result["title"] = _fallback_title(html)
            if not result["text"]:
                result["error"] = "trafilatura returned no text for this document"
            return result
        except ImportError:
            return {
                "title": _fallback_title(html),
                "text": "",
                "author": None,
                "date": None,
                "language": None,
                "url": url,
                "error": "trafilatura is not installed",
            }
        except Exception as exc:
            return {
                "title": _fallback_title(html),
                "text": "",
                "author": None,
                "date": None,
                "language": None,
                "url": url,
                "error": f"extraction failed: {exc}",
            }
