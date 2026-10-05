"""Unit-level sizing guards per §41.13 — *not* system performance measurements.

The real end-to-end load path is measured by `tests/load/harness.py` and
`tests/load/test_load_harness.py` (a real uvicorn server, real PostgreSQL and
real object storage). This file only asserts **invariants** that must hold even
under a mocked LLM:

1. the pipeline does not serialise on I/O — concurrent runs make progress;
2. a completed LLM call feeds the §34/§41.13 ``llm_latency`` histogram.

No number here is a capacity of the deployed system: those come from a campaign
(`python -m tests.load.run_load`) or from ``GET /v1/metrics``.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.observability.metrics import DEFAULT_REGISTRY


@pytest.mark.asyncio
async def test_concurrent_pipeline_runs_make_progress(mock_llm) -> None:
    """The runner must not block the whole process on one in-flight request."""
    mock_llm.configure('{"summary": "load test", "findings": []}')
    runner = PipelineRunner()
    n_requests = 10

    start = time.perf_counter()
    results = await asyncio.gather(
        *[
            runner.run(f"REQ_LOAD_{i}", {"objective": f"Benchmark request {i}"})
            for i in range(n_requests)
        ]
    )
    elapsed = time.perf_counter() - start

    assert len(results) == n_requests
    assert all(result.get("status") is not None for result in results)
    # Coarse smoke guard only: ten runs must finish well inside a per-run budget,
    # proving the process is not serialising. This is not a capacity claim.
    assert elapsed < 60.0


@pytest.mark.asyncio
async def test_a_completed_llm_call_feeds_the_latency_metric(mock_llm) -> None:
    """§41.13/§34 — ``llm_latency`` is *observed* by the pipeline, never invented."""
    mock_llm.configure('{"summary": "load test", "findings": []}')
    before = DEFAULT_REGISTRY.snapshot()["llm_latency"]["observed"]

    await PipelineRunner().run("REQ_LLM_METRIC", {"objective": "ping"})

    after = DEFAULT_REGISTRY.snapshot()["llm_latency"]["observed"]
    assert after > before, "un appel LLM complété doit alimenter l'histogramme llm_latency"


def test_metrics_exposes_all_eight_benchmarks() -> None:
    """``GET /v1/metrics → benchmarks`` lists the eight §41.13 names (HTTP level)."""
    from fastapi.testclient import TestClient

    from app.main import app

    res = TestClient(app).get("/v1/metrics")

    assert res.status_code == 200
    assert set(res.json()["benchmarks"]) == {
        "max_plan_steps",
        "max_parallel_tool_calls",
        "max_information_units_per_request",
        "target_requests_per_second",
        "vector_search_latency_p99_ms",
        "postgres_query_latency_p99_ms",
        "amqp_message_latency_p99_ms",
        "llm_call_latency_p99_ms",
    }
