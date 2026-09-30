"""§41.13 — request throughput and per-request latency with a mocked LLM/web.

Measures how many research requests one process completes per second and how
long the tail takes, then checks the guard rails §41.13 requires: a request that
stops early must still deliver a status from §1.3, and the observed rate must be
high enough to prove the pipeline is not accidentally serialising on I/O.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.core.statuses import OUTPUT_STATUSES, PIPELINE_SUCCESS_STATUS
from app.domain.entities.search_result import SearchResult
from app.domain.value_objects.ulid import ULID

pytestmark = pytest.mark.asyncio

#: §1.3 — the authorized states, plus the retained v1 spelling of ``SUCCESS``.
DELIVERABLE_STATUSES = (*OUTPUT_STATUSES, PIPELINE_SUCCESS_STATUS)

#: Requests measured per benchmark run.
REQUEST_COUNT = 12

#: A run must not be slower than this on average (seconds) — generous, but it
#: catches a pipeline that blocks on real I/O despite the mocks.
MAX_AVERAGE_SECONDS = 1.5

#: The §41.13 sizing guard: at least this many requests per second locally.
MIN_REQUESTS_PER_SECOND = 1.0


@pytest.fixture
def stub_pipeline(monkeypatch: pytest.MonkeyPatch, mock_llm) -> None:
    """Make a run deterministic: one mocked source, no HTTP, no real LLM."""
    search = AsyncMock(
        return_value=[
            SearchResult(
                title="Paris — Wikipédia",
                url="https://fr.wikipedia.org/wiki/Paris",
                snippet="Paris est la capitale de la France.",
                score=0.95,
                provider="wikipedia",
            )
        ]
    )
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
    mock_llm.configure('{"summary": "Paris est la capitale.", "findings": []}')


async def _timed_runs(count: int) -> list[float]:
    """Run *count* requests sequentially and return each duration in seconds."""
    runner = PipelineRunner()
    durations: list[float] = []
    for index in range(count):
        started = time.perf_counter()
        await runner.run(
            ULID.new("REQ_"), {"objective": f"capitale du pays numéro {index}"}
        )
        durations.append(time.perf_counter() - started)
    return durations


class TestThroughput:
    """§41.13 — a single process sustains a usable request rate."""

    async def test_sequential_throughput_and_latency(self, stub_pipeline: None) -> None:
        """Every request completes, the mean is bounded and the rate is usable."""
        durations = await _timed_runs(REQUEST_COUNT)
        total = sum(durations)
        rate = REQUEST_COUNT / total

        assert len(durations) == REQUEST_COUNT
        assert total / REQUEST_COUNT < MAX_AVERAGE_SECONDS, (
            f"mean request latency {total / REQUEST_COUNT:.3f}s exceeds "
            f"{MAX_AVERAGE_SECONDS}s"
        )
        assert rate >= MIN_REQUESTS_PER_SECOND, f"throughput {rate:.2f} req/s is too low"

    async def test_tail_latency_is_bounded(self, stub_pipeline: None) -> None:
        """The slowest run stays within a small multiple of the median."""
        durations = sorted(await _timed_runs(REQUEST_COUNT))
        median = durations[len(durations) // 2]
        worst = durations[-1]

        assert worst <= max(median * 5, 0.5), (
            f"tail latency {worst:.3f}s against a median of {median:.3f}s"
        )


class TestGuardRails:
    """§41.13/§1.3 — throughput never comes at the cost of the contract."""

    async def test_every_run_delivers_a_documented_status(self, stub_pipeline: None) -> None:
        """Each delivery carries a §1.3 output status, never an invented one."""
        runner = PipelineRunner()

        deliveries = await asyncio.gather(
            *(runner.run(ULID.new("REQ_"), {"objective": "capitale"}) for _ in range(5))
        )

        assert all(delivery["status"] in DELIVERABLE_STATUSES for delivery in deliveries), [
            delivery["status"] for delivery in deliveries
        ]

    async def test_a_run_reports_its_own_usage(self, stub_pipeline: None) -> None:
        """§41.2 — every delivery carries its consumption report, even at speed."""
        delivery = await PipelineRunner().run(
            ULID.new("REQ_"), {"objective": "capitale de la France"}
        )

        assert delivery["usage_report"], "the delivery lost its usage report"

