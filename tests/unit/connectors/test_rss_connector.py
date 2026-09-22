"""Tests for RSSConnector per §9.1 (MockTransport, RSS 2.0 + Atom)."""

import httpx
import pytest

from app.connectors.base import Query, RawSource, SourceCandidate
from app.connectors.web.rss_connector import RSSConnector

FEED_URL = "https://example.com/feed.xml"

RSS_DOC = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Example feed</title>
<item><title>First news</title><link>https://example.com/1</link>
<pubDate>Tue, 16 Sep 2026 10:00:00 +0000</pubDate></item>
<item><title>Second news</title><link>https://example.com/2</link>
<pubDate>Wed, 17 Sep 2026 10:00:00 +0000</pubDate></item>
</channel></rss>
"""

ATOM_DOC = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Example atom</title>
<entry><title>Atom entry</title><link href="https://example.com/a"/>
<updated>2026-09-17T10:00:00Z</updated></entry>
</feed>
"""


def _client(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_rss_discover() -> None:
    """Each RSS 2.0 entry becomes a candidate with title and date."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=RSS_DOC, headers={"content-type": "application/rss+xml"})

    candidates = await RSSConnector(client=_client(handler)).discover(
        Query(query_string=FEED_URL)
    )

    assert len(candidates) == 2
    assert candidates[0].location == "https://example.com/1"
    assert candidates[0].metadata["title"] == "First news"
    assert "2026" in candidates[0].metadata["published"]


@pytest.mark.asyncio
async def test_rss_retrieve() -> None:
    """Entry pages are retrieved raw with origin URL for provenance."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>article</html>")

    raw = await RSSConnector(client=_client(handler)).retrieve(
        SourceCandidate(source_id="rss-0-first-news", location="https://example.com/1", metadata={})
    )

    assert "article" in raw.data
    assert raw.metadata["source_url"] == "https://example.com/1"
    assert raw.metadata["data_stage"] == "raw"


@pytest.mark.asyncio
async def test_rss_inspect_atom() -> None:
    """Atom payloads report format, item count and latest date."""
    connector = RSSConnector(
        client=_client(lambda r: httpx.Response(200, text="<html/>"))
    )
    # Inspect a real Atom payload directly (retrieve path is covered above).
    feed_raw = RawSource(
        source_id="rss-feed", data=ATOM_DOC, content_type="application/atom+xml", metadata={}
    )
    metadata = await connector.inspect(feed_raw)

    assert metadata.record_count == 1
    assert metadata.schema is not None
    assert metadata.schema["format"] == "atom"
    assert metadata.schema["latest_item_date"].startswith("2026-09-17")


@pytest.mark.asyncio
async def test_rss_inspect_rss_counts_and_latest() -> None:
    """RSS 2.0 payloads report item count and the latest pubDate."""
    connector = RSSConnector(
        client=_client(lambda r: httpx.Response(200, text="<html/>"))
    )
    feed_raw = RawSource(
        source_id="rss-feed", data=RSS_DOC, content_type="application/rss+xml", metadata={}
    )
    metadata = await connector.inspect(feed_raw)

    assert metadata.record_count == 2
    assert metadata.schema is not None
    assert metadata.schema["format"] == "rss2.0"
    assert metadata.schema["latest_item_date"].startswith("2026-09-17")
