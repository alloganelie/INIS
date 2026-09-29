"""§24.1 — the delivered information package, seen from the HTTP contract.

A client that submitted a request must be able to read back *what INIS
delivered*, not only the status: the units, the evidence, the confidence block
and the provenance. The package is produced by the pipeline and exposed through
``GET /v1/requests/{id}`` (``pipeline_state``); these tests drive a real run with
mocked providers and then validate the HTTP-visible package against the §24.1
contract and the §1 ``InformationPackage`` domain entity.

Mocked providers only — no Docker, no network.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1.requests.pipeline_runner import pipeline_runner
from app.domain.entities.information_package import InformationPackage
from app.domain.entities.search_result import SearchResult
from app.domain.value_objects.ulid import ULID
from app.main import app

client = TestClient(app)

OBJECTIVE = "Quelle est la capitale de la France ?"

#: The §15.1 dimensions every delivery must report.
CONFIDENCE_DIMENSIONS = (
    "source_reliability",
    "source_freshness",
    "extraction_confidence",
    "data_quality",
    "evidence_strength",
    "cross_source_agreement",
    "methodological_consistency",
)


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
    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search", search
    )
    monkeypatch.setattr(
        "app.connectors.web.extractors.wikipedia_extractor.WikipediaExtractor.extract",
        extract,
    )
    return {"search": search, "extract": extract}


async def _deliver(objective: str = OBJECTIVE) -> tuple[str, dict]:
    """Create a request through the API, run the pipeline, return id + package."""
    created = client.post(
        "/v1/requests",
        json={"objective": objective, "request_type": "research"},
    )
    assert created.status_code == 201
    request_id = created.json()["request_id"]
    delivery = await pipeline_runner.run(request_id, {"objective": objective})
    return request_id, delivery


class TestDeliveredPackageIsReadable:
    """§24.1 — what the pipeline delivered is what the API exposes."""

    async def test_get_request_exposes_the_delivered_package(
        self, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        """``GET /v1/requests/{id}`` carries the delivered units and provenance."""
        mock_llm.configure('{"summary": "Paris est la capitale.", "findings": []}')
        request_id, delivery = await _deliver()

        response = client.get(f"/v1/requests/{request_id}")

        assert response.status_code == 200
        package = response.json()["pipeline_state"]
        assert package is not None, "a completed run must expose its delivery"
        assert package["request_id"] == request_id
        assert package["information_units"] == delivery["information_units"]
        assert package["provenance"]["request_id"] == request_id

    async def test_package_units_are_all_traceable(
        self, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        """§0.2/§11 — every delivered unit names the source it came from."""
        mock_llm.configure('{"summary": "Paris est la capitale.", "findings": []}')
        _, delivery = await _deliver()

        units = delivery["information_units"]
        assert units, "the delivery delivered no unit to inspect"
        for unit in units:
            provenance = unit.get("provenance") or {}
            assert provenance, f"unit {unit['information_id']} has no provenance"
            assert str(unit["source_id"]).startswith("SRC_")
            assert (
                provenance.get("source_id")
                or provenance.get("extracted_from")
                or provenance.get("url")
            ), f"unit {unit['information_id']} does not say where it came from"

    async def test_package_confidence_is_not_a_probability(
        self, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        """§15 — the delivered confidence reports its dimensions and its nature."""
        mock_llm.configure('{"summary": "Paris est la capitale.", "findings": []}')
        _, delivery = await _deliver()

        confidence = delivery["confidence"]
        assert confidence["not_a_probability"] is True
        assert set(confidence["dimensions"]) == set(CONFIDENCE_DIMENSIONS)
        assert 0.0 <= confidence["score"] <= 1.0

    async def test_package_satisfies_the_domain_contract(
        self, web_doubles: dict[str, AsyncMock], mock_llm
    ) -> None:
        """§1 — the HTTP package is a valid ``InformationPackage``."""
        mock_llm.configure('{"summary": "Paris est la capitale.", "findings": []}')
        request_id, delivery = await _deliver()

        package = InformationPackage(
            package_id=delivery["response_id"],
            request_id=request_id,
            units=delivery["information_units"],
            confidence=delivery["confidence"],
            provenance=delivery["provenance"],
            created_at=datetime.now(UTC),
            data_stage="raw",
        )
        package.validate()

        assert package.units == delivery["information_units"]

    async def test_unknown_request_is_not_reported_as_delivered(self) -> None:
        """A package is never invented for a request the API never accepted."""
        response = client.get(f"/v1/requests/{ULID.new('REQ_')}")

        assert response.status_code == 404

