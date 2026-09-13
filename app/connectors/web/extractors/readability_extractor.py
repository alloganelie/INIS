"""Article-text extractor over readability-lxml (§9.1: pages Web).

``readability`` is imported lazily inside :meth:`ReadabilityExtractor.extract`
so this module stays importable where the optional dependency is missing.
readability-lxml extracts title and main content but no author/date
metadata (those fields stay None by design). On any failure a graceful
fallback returns the contract dict with an ``error`` message instead of
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


def _strip_tags(html: str) -> str:
    """Reduce an HTML fragment to plain text (whitespace collapsed)."""
    text = _TAG_RE.sub(" ", html)
    return re.sub(r"\s+", " ", text).strip()


class ReadabilityExtractor:
    """Extract main article text and title from raw HTML."""

    async def extract(self, html: str, url: str) -> dict[str, Any]:
        """Extract ``{title, text, author, date}`` (+ url, error).

        Never raises on extraction failure or empty HTML: returns the
        contract dict with ``error`` set. Raises ``ValueError`` only
        when ``html``/``url`` are not strings.
        """
        if not isinstance(html, str):
            raise ValueError("html must be a string")
        if not isinstance(url, str) or not url:
            raise ValueError("url must be a non-empty string")
        if not html:
            return {
                "title": None,
                "text": "",
                "author": None,
                "date": None,
                "url": url,
                "error": "empty html",
            }
        try:
            from readability import Document

            document = Document(html)
            title = document.title() or _fallback_title(html)
            text = _strip_tags(document.summary())
            result: dict[str, Any] = {
                "title": title,
                "text": text,
                "author": None,
                "date": None,
                "url": url,
                "error": None,
            }
            if not text:
                result["error"] = "readability returned no text for this document"
            return result
        except ImportError:
            return {
                "title": _fallback_title(html),
                "text": "",
                "author": None,
                "date": None,
                "url": url,
                "error": "readability is not installed",
            }
        except Exception as exc:
            return {
                "title": _fallback_title(html),
                "text": "",
                "author": None,
                "date": None,
                "url": url,
                "error": f"extraction failed: {exc}",
            }
