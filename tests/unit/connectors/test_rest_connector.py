"""Tests for RESTConnector per §9 (httpx MockTransport, no network)."""

import httpx

from app.connectors.api.rest_connector import RESTConnector
from app.connectors.base import Query
from app.connectors.base import SourceCandidate


def _client(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


class TestRestConnector:
    """3 tests covering discover, retrieve and health_check."""

    async def test_discover_returns_candidates(self) -> None:
        """discover maps the /search payload to base.SourceCandidate."""

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/search"
            assert request.url.params["q"] == "climate"
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "1",
                            "title": "Climate data",
                            "url": "https://api.example.com/items/1",
                        }
                    ]
                },
            )

        connector = RESTConnector(base_url="https://api.example.com", client=_client(handler))
        candidates = await connector.discover(Query(query_string="climate"))

        assert len(candidates) == 1
        assert candidates[0].source_id == "1"
        assert candidates[0].location == "https://api.example.com/items/1"

    async def test_retrieve_returns_raw_source_with_provenance(self) -> None:
        """retrieve returns a base.RawSource tracing its origin URL."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text='{"temp": 21}', headers={"content-type": "application/json"})

        connector = RESTConnector(base_url="https://api.example.com", client=_client(handler))
        raw = await connector.retrieve(
            SourceCandidate(
                source_id="1",
                location="https://api.example.com/items/1",
                metadata={},
            )
        )

        assert raw.source_id == "1"
        assert raw.metadata["source_url"] == "https://api.example.com/items/1"
        assert raw.metadata["data_stage"] == "raw"

    async def test_health_check_reports_down_on_failure(self) -> None:
        """health_check reports unhealthy (never raises) when the probe fails."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        connector = RESTConnector(base_url="https://api.example.com", client=_client(handler))
        status = await connector.health_check()

        assert status.healthy is False
        assert "down" in status.message
