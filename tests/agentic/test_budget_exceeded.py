"""§41.2 scenario — « budget dépassé ».

A request whose budget is exhausted must stop metered work, still deliver a
complete payload, and say so explicitly: the §1.3 status becomes
``BUDGET_EXCEEDED``, the §41.2 usage report flags the exhausted dimension and
the limitations block names it — never a silent overspend, never a crash.

Mocked providers only — no Docker, no network.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.core.statuses import BUDGET_EXCEEDED_STATUS, OUTPUT_STATUSES
from app.domain.entities.search_result import SearchResult
from app.domain.value_objects.ulid import ULID

OBJECTIVE = "Quelle est la capitale de la France ?"


@pytest.fixture
def web_doubles(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Mock the §9/§10 providers and extractor used by the acquisition stage."""
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


async def _run(
    runner: PipelineRunner, payload: dict[str, Any]
) -> dict[str, Any]:
    return await runner.run(ULID.new("REQ_"), payload)


@pytest.mark.asyncio
async def test_zero_web_budget_stops_acquisition_before_any_request(
    web_doubles: dict[str, AsyncMock],
) -> None:
    """An exhausted ``web_requests`` budget halts the run and is reported (§41.2)."""
    runner = PipelineRunner()

    out = await _run(
        runner,
        {"objective": OBJECTIVE, "budget": {"max_web_requests": 0}},
    )

    assert out["status"] == BUDGET_EXCEEDED_STATUS
    assert BUDGET_EXCEEDED_STATUS in OUTPUT_STATUSES
    # The metered request never leaves the process over budget.
    assert web_doubles["search"].await_count == 0

    report = out["usage_report"]
    assert report["status"] == BUDGET_EXCEEDED_STATUS
    assert report["exceeded"] == "web_requests"
    assert report["budget"]["max_web_requests"] == 0
    assert any(
        "Budget §41.2 dépassé sur 'web_requests'" in limitation
        for limitation in out["limitations"]
    ), "the breached dimension must be named in the delivery"


@pytest.mark.asyncio
async def test_budget_breach_still_delivers_a_complete_payload(
    web_doubles: dict[str, AsyncMock],
) -> None:
    """The breach is reported, never raised: the delivery stays a full §24 payload."""
    runner = PipelineRunner()
    request_id = ULID.new("REQ_")

    out = await runner.run(
        request_id,
        {"objective": OBJECTIVE, "budget": {"max_web_requests": 0}},
    )

    for key in (
        "summary",
        "findings",
        "sources",
        "limitations",
        "usage_report",
        "confidence",
    ):
        assert key in out, f"a budget breach must not strip the delivery of {key!r}"
    assert out["provenance"]["request_id"] == request_id
    assert out["usage_report"]["web_requests"] >= 1, "the refused charge is accounted"


@pytest.mark.asyncio
async def test_within_budget_run_is_not_flagged(
    web_doubles: dict[str, AsyncMock],
) -> None:
    """Control: an unbounded run searches normally and reports ``within_budget``."""
    runner = PipelineRunner()

    out = await _run(runner, {"objective": OBJECTIVE})

    assert out["status"] != BUDGET_EXCEEDED_STATUS
    assert web_doubles["search"].await_count >= 1, "no budget → the search is performed"
    report = out["usage_report"]
    assert report["status"] == "within_budget"
    assert report["exceeded"] is None
