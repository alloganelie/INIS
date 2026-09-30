"""§32/§1.3 — cancelling an Information Request is a real, idempotent transition.

``POST /v1/requests/{id}/cancel`` exists in the router but no test ever drove it,
so nothing proved that the §1.3 ``CANCELLED`` state is what a client actually
receives — nor that cancelling twice, or cancelling an unknown id, behaves
honestly instead of silently succeeding.

Note that ``POST /v1/requests`` schedules the pipeline as a §28 background task,
so creating a request here also executes a run; cancellation is therefore
exercised both on a request whose run already delivered and on a bare one.

Mocked providers only — no Docker, no network.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1.requests.pipeline_runner import pipeline_runner
from app.core.statuses import CANCELLED_STATUS, OUTPUT_STATUSES
from app.domain.entities.search_result import SearchResult
from app.domain.value_objects.ulid import ULID
from app.main import app

client = TestClient(app)

OBJECTIVE = "Quelle est la capitale de la France ?"


@pytest.fixture
def web_doubles(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Serve one traceable source through the §9/§10 providers."""
    result = SearchResult(
        title="Paris — Wikipédia",
        url="https://fr.wikipedia.org/wiki/Paris",
        snippet="Paris est la capitale de la France.",
        score=0.95,
        provider="wikipedia",
    )
    search = AsyncMock(return_value=[result])
    extract = AsyncMock(
        return_value={
            "title": "Paris",
            "text": "Paris est la capitale de la France.",
            "language": "fr",
            "url": "https://fr.wikipedia.org/wiki/Paris",
            "error": None,
        }
    )
    monkeypatch.setattr("app.connectors.web.provider_router.ProviderRouter.search", search)
    monkeypatch.setattr(
        "app.connectors.web.extractors.wikipedia_extractor.WikipediaExtractor.extract",
        extract,
    )
    return {"search": search, "extract": extract}


def _create(objective: str = OBJECTIVE) -> str:
    """Create a request through the API and return its identifier."""
    created = client.post(
        "/v1/requests",
        json={"objective": objective, "request_type": "research"},
    )
    assert created.status_code == 201
    return created.json()["request_id"]


class TestCancelContract:
    """§32 — the endpoint returns the new §1.3 state of the request."""

    def test_cancelling_a_request_reports_the_cancelled_status(self) -> None:
        """A cancellation is reported as ``CANCELLED``, a §1.3 authorized state."""
        request_id = _create()

        response = client.post(f"/v1/requests/{request_id}/cancel")

        assert response.status_code == 200
        body = response.json()
        assert body["request_id"] == request_id
        assert body["status"] == CANCELLED_STATUS
        assert body["status"] in OUTPUT_STATUSES
        assert body["pipeline_state"]["current_step"] == "cancelled"
        assert body["pipeline_state"]["cancelled_at"], "the cancellation is not timestamped"

    def test_cancellation_is_idempotent(self) -> None:
        """Cancelling twice returns the same state instead of failing (§32)."""
        request_id = _create()

        first = client.post(f"/v1/requests/{request_id}/cancel")
        second = client.post(f"/v1/requests/{request_id}/cancel")

        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["status"] == CANCELLED_STATUS
        assert second.json()["status"] == CANCELLED_STATUS

    def test_cancelled_request_reads_back_as_cancelled(self) -> None:
        """The cancellation is not forgotten by the next read."""
        request_id = _create()
        client.post(f"/v1/requests/{request_id}/cancel")

        read = client.get(f"/v1/requests/{request_id}")

        assert read.status_code == 200
        assert read.json()["status"] == CANCELLED_STATUS

    def test_unknown_request_is_not_reported_as_cancelled(self) -> None:
        """An unknown id is a 404, never a silent success."""
        unknown = ULID.new("REQ_")

        response = client.post(f"/v1/requests/{unknown}/cancel")

        assert response.status_code == 404
        assert unknown in response.json()["detail"]

    def test_cancellation_is_recorded_on_the_runner(self) -> None:
        """§32 — the flag is set and the response is the runner's own state."""
        request_id = _create()
        assert pipeline_runner.is_cancelled(request_id) is False

        body = client.post(f"/v1/requests/{request_id}/cancel").json()

        assert pipeline_runner.is_cancelled(request_id) is True
        assert body["pipeline_state"] == pipeline_runner.get_state(request_id)


class TestCancelAfterDelivery:
    """§1.3 — a cancelled run still reports what it had already obtained."""

    async def test_cancel_keeps_the_units_already_delivered(
        self, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        """Cancellation overrides the status without dropping the material."""
        mock_llm.configure('{"summary": "Paris est la capitale.", "findings": []}')
        request_id = _create()
        delivery = await pipeline_runner.run(request_id, {"objective": OBJECTIVE})
        assert delivery["information_units"], "the run delivered nothing to cancel"

        body = client.post(f"/v1/requests/{request_id}/cancel").json()

        assert body["status"] == CANCELLED_STATUS
        assert [
            unit["information_id"] for unit in body["pipeline_state"]["information_units"]
        ] == [unit["information_id"] for unit in delivery["information_units"]]
