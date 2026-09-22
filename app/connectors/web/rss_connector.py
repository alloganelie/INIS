"""RSS/Atom feed connector over httpx (§9.1: flux RSS/Atom).

Stdlib ``xml.etree`` only (no feedparser dependency): supports RSS 2.0
(``channel/item``) and Atom (``feed/entry``, namespaced or not).
``discover`` fetches the feed URL carried by the query and returns one
candidate per entry; ``retrieve`` fetches the entry link; ``inspect``
reports item count and latest date for feed payloads.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import httpx

from app.connectors.base import (
    ConnectorMetadata,
    HealthStatus,
    Query,
    RawSource,
    SourceCandidate,
    SourceConnector,
    SourceMetadata,
)
from app.core.errors import InfrastructureError

_ATOM_NS = "http://www.w3.org/2005/Atom"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _local(tag: str) -> str:
    """Return the local tag name without any namespace."""
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _slug(title: str, index: int) -> str:
    """Build a URL-safe slug from a title (fallback to item index)."""
    slug = _SLUG_RE.sub("-", title.strip().lower()).strip("-")[:40]
    return slug or f"item-{index}"


def _parse_date(value: str | None) -> datetime | None:
    """Parse an RSS (RFC 822) or Atom (ISO 8601) date, else None."""
    if not value or not value.strip():
        return None
    text = value.strip()
    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError):
        pass
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_feed(data: bytes) -> tuple[str, list[dict[str, str]]]:
    """Parse RSS 2.0 or Atom payload.

    Args:
        data: Raw feed bytes.

    Returns:
        Tuple of (format "rss2.0"|"atom", items with title/link/date).

    Raises:
        ET.ParseError: If the payload is not parseable XML.
        ValueError: If the root element is neither RSS nor Atom feed.
    """
    root = ET.fromstring(data)
    name = _local(root.tag)
    items: list[dict[str, str]] = []
    if name == "rss":
        feed_format = "rss2.0"
        channel = root.find("channel")
        entries = channel.findall("item") if channel is not None else []
        for entry in entries:
            title = (entry.findtext("title") or "").strip()
            link = (entry.findtext("link") or "").strip()
            date = (entry.findtext("pubDate") or "").strip()
            items.append({"title": title, "link": link, "date": date})
    elif name == "feed":
        feed_format = "atom"
        entries = [el for el in root if _local(el.tag) == "entry"]
        for entry in entries:
            title = (
                entry.findtext(f"{{{_ATOM_NS}}}title")
                or entry.findtext("title")
                or ""
            ).strip()
            link = ""
            for link_el in entry:
                if _local(link_el.tag) == "link" and link_el.get("href"):
                    link = link_el.get("href", "").strip()
                    break
            date = (
                entry.findtext(f"{{{_ATOM_NS}}}updated")
                or entry.findtext("updated")
                or entry.findtext(f"{{{_ATOM_NS}}}published")
                or entry.findtext("published")
                or ""
            ).strip()
            items.append({"title": title, "link": link, "date": date})
    else:
        raise ValueError(f"Unsupported feed root element: {root.tag}")
    return feed_format, items


class RSSConnector:
    """RSS 2.0 + Atom feed connector (httpx + stdlib ElementTree)."""

    connector_id: str = "rss-connector"
    supported_source_types: list[str] = ["rss", "atom"]

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self._client = client
        self._timeout_seconds = timeout_seconds

    async def _get(self, url: str, client: httpx.AsyncClient | None = None) -> httpx.Response:
        """GET a URL, wrapping transport errors as InfrastructureError."""
        http_client = client or self._client or httpx.AsyncClient(
            timeout=self._timeout_seconds
        )
        try:
            response = await http_client.get(url)
            response.raise_for_status()
        except Exception as exc:
            raise InfrastructureError(f"RSS fetch failed for {url}: {exc}") from exc
        return response

    async def discover(self, query: Query) -> list[SourceCandidate]:
        """Fetch the feed URL from the query; one candidate per entry.

        Args:
            query: Query whose ``query_string`` is the feed URL.

        Returns:
            List of source candidates (one per feed entry with a link).
        """
        feed_url = query.query_string.strip()
        if not feed_url.startswith(("http://", "https://")):
            raise ValueError("query_string must be an http(s) feed URL")
        response = await self._get(feed_url)
        try:
            _, items = _parse_feed(response.content)
        except (ET.ParseError, ValueError) as exc:
            raise InfrastructureError(f"RSS discover failed: not a feed: {exc}") from exc
        candidates: list[SourceCandidate] = []
        for index, item in enumerate(items):
            if not item["link"]:
                continue
            candidates.append(
                SourceCandidate(
                    source_id=f"rss-{index}-{_slug(item['title'], index)}",
                    location=item["link"],
                    metadata={
                        "title": item["title"],
                        "published": item["date"],
                        "feed_url": feed_url,
                    },
                )
            )
        return candidates

    async def retrieve(self, candidate: SourceCandidate) -> RawSource:
        """Fetch the raw entry page behind a candidate (stays ``raw``).

        Args:
            candidate: Source candidate to retrieve.

        Returns:
            Raw source data with origin URL for provenance.
        """
        response = await self._get(candidate.location)
        return RawSource(
            source_id=candidate.source_id,
            data=response.text,
            content_type=response.headers.get("content-type", "text/html"),
            metadata={
                "source_url": candidate.location,
                "status_code": str(response.status_code),
                "data_stage": "raw",
            },
        )

    async def inspect(self, raw: RawSource) -> SourceMetadata:
        """Inspect a feed payload: item count and latest item date.

        Args:
            raw: Raw source data.

        Returns:
            Source metadata (size-only when the payload is not a feed).
        """
        payload = raw.data.encode("utf-8") if isinstance(raw.data, str) else bytes(raw.data)
        try:
            feed_format, items = _parse_feed(payload)
        except (ET.ParseError, ValueError):
            return SourceMetadata(
                source_id=raw.source_id,
                size_bytes=len(payload),
                record_count=0,
            )
        latest: datetime | None = None
        for item in items:
            parsed = _parse_date(item["date"])
            if parsed is not None and (latest is None or parsed > latest):
                latest = parsed
        schema = {"format": feed_format}
        if latest is not None:
            schema["latest_item_date"] = latest.isoformat()
        return SourceMetadata(
            source_id=raw.source_id,
            size_bytes=len(payload),
            record_count=len(items),
            schema=schema,
        )

    async def health_check(self) -> HealthStatus:
        """Check if the connector is healthy (no I/O).

        Returns:
            Health status.
        """
        return HealthStatus(healthy=True, message="RSS connector healthy")

    async def metadata(self) -> ConnectorMetadata:
        """Get connector metadata.

        Returns:
            Connector metadata.
        """
        return ConnectorMetadata(
            connector_id=self.connector_id,
            name="RSS Connector",
            version="1.0.0",
            supported_source_types=self.supported_source_types,
        )
