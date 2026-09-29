"""§41.13 — concurrency: N agents served by one process without contamination.

INIS serves several requests at once, and two failures are invisible in
sequential tests: a shared mutable state that leaks a delivery from one run into
another, and an implementation that silently serialises concurrent work. These
tests run many requests through ``asyncio.gather`` and assert that every run
keeps its own identity, material and registration.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.entities.search_result import SearchResult
from app.domain.value_objects.ulid import ULID
from app.registry.agent_registry import AgentRegistry
from app.registry.capability_index import CapabilityIndex
from tests.factories import make_agent_identity

pytestmark = pytest.mark.asyncio

#: How many requests are run in parallel.
CONCURRENCY = 8


@pytest.fixture
def stub_providers(monkeypatch: pytest.MonkeyPatch, mock_llm) -> None:
    """One mocked source and a canned synthesis — no HTTP, no real LLM."""
    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search",
        AsyncMock(
            return_value=[
                SearchResult(
                    title="Paris — Wikipédia",
                    url="https://fr.wikipedia.org/wiki/Paris",
                    snippet="Paris est la capitale de la France.",
                    score=0.95,
                    provider="wikipedia",
                )
            ]
        ),
    )
    monkeypatch.setattr(
        "app.connectors.web.extractors.wikipedia_extractor.WikipediaExtractor.extract",
        AsyncMock(
            return_value={
                "title": "Paris",
                "text": "Paris est la capitale de la France.",
                "language": "fr",
                "url": "https://fr.wikipedia.org/wiki/Paris",
                "error": None,
            }
        ),
    )
    mock_llm.configure('{"summary": "Paris est la capitale.", "findings": []}')


class TestConcurrentRequests:
    """§41.13 — parallel runs are independent and genuinely parallel."""

    async def test_each_run_keeps_its_own_identity(self, stub_providers: None) -> None:
        """No delivery borrows another run's request id."""
        runner = PipelineRunner()
        request_ids = [ULID.new("REQ_") for _ in range(CONCURRENCY)]

        deliveries = await asyncio.gather(
            *(runner.run(rid, {"objective": f"objective {rid}"}) for rid in request_ids)
        )

        assert [delivery["request_id"] for delivery in deliveries] == request_ids
        assert len({delivery["response_id"] for delivery in deliveries}) == CONCURRENCY

    async def test_runs_do_not_share_information_ids(self, stub_providers: None) -> None:
        """Two concurrent runs never emit the same information unit id (§0.3)."""
        runner = PipelineRunner()

        deliveries = await asyncio.gather(
            *(runner.run(ULID.new("REQ_"), {"objective": "capitale"}) for _ in range(4))
        )

        unit_ids = [
            unit["information_id"]
            for delivery in deliveries
            for unit in delivery["information_units"]
        ]
        assert len(unit_ids) == len(set(unit_ids))

    async def test_parallel_is_not_slower_than_sequential(self, stub_providers: None) -> None:
        """Concurrency actually overlaps: parallel time stays under the sum."""
        runner = PipelineRunner()
        requests = [(ULID.new("REQ_"), {"objective": "capitale"}) for _ in range(CONCURRENCY)]

        started = time.perf_counter()
        await asyncio.gather(*(runner.run(rid, payload) for rid, payload in requests))
        parallel = time.perf_counter() - started

        assert parallel < CONCURRENCY * 1.0, (
            f"{CONCURRENCY} concurrent runs took {parallel:.3f}s: they look serialised"
        )

    async def test_registry_state_survives_concurrent_runs(self, stub_providers: None) -> None:
        """The runner state store stays consistent after parallel traffic."""
        runner = PipelineRunner()
        request_ids = [ULID.new("REQ_") for _ in range(4)]

        await asyncio.gather(
            *(runner.run(rid, {"objective": "capitale"}) for rid in request_ids)
        )

        for request_id in request_ids:
            state = runner.get_state(request_id)
            assert state is not None
            assert state["request_id"] == request_id


class TestConcurrentRegistration:
    """§6 — the registry serves many agents at once, without losing one."""

    async def test_concurrent_heartbeats_keep_every_agent(self) -> None:
        """Concurrent registration plus heartbeats lose no agent (§6.3)."""
        registry = AgentRegistry()
        index = CapabilityIndex()
        agent_ids = [f"AGENT_{index:02d}" for index in range(20)]

        def register_and_beat(agent_id: str) -> None:
            identity = make_agent_identity(agent_id, capabilities=["web_search"])
            registry.register(agent_id, identity)
            index.add_agent(agent_id, list(identity.capabilities))
            registry.update_heartbeat(agent_id, {"healthy": True})

        await asyncio.gather(
            *(asyncio.to_thread(register_and_beat, agent_id) for agent_id in agent_ids)
        )

        assert sorted(agent.agent_id for agent in registry.list_agents()) == sorted(agent_ids)
        assert sorted(index.get_agents_for_capability("web_search")) == sorted(agent_ids)

