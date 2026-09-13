"""Tests for RESTConnector per §9 (httpx MockTransport, no network)."""

import httpx

from app.connectors.api.rest_connector import RESTConnector


def _client(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


class TestRestConnector:
    """3 tests covering discover, retrieve and health_check."""

    async def test_discover_returns_candidates(self) -> None:
        """discover maps the /search payload to candidate dicts."""

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/search"
            assert request.url.params["q"] == "climate"
            return httpx.Response(200, json={"items": [{"id": "1", "title": "Climate data"}]})

        connector = RESTConnector(base_url="https://api.example.com", client=_client(handler))
        candidates = await connector.discover("climate")

        assert candidates == [{"id": "1", "title": "Climate data"}]

    async def test_retrieve_returns_raw_source_with_provenance(self) -> None:
        """retrieve keeps data_stage raw and records the source URL."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text='{"temp": 21}', headers={"content-type": "application/json"})

        connector = RESTConnector(base_url="https://api.example.com", client=_client(handler))
        raw = await connector.retrieve({"url": "https://api.example.com/items/1"})

        assert raw["data_stage"] == "raw"
        assert raw["source_url"] == "https://api.example.com/items/1"
        assert raw["status_code"] == 200

    async def test_health_check_reports_down_on_failure(self) -> None:
        """health_check reports down (never raises) when the probe fails."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        connector = RESTConnector(base_url="https://api.example.com", client=_client(handler))
        status = await connector.health_check()

        assert status["status"] == "down"
        assert status["connector_id"] == "rest-connector"
