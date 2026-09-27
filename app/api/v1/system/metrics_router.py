"""Metrics router exposing system observability metrics per §32 and §34."""

from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter

from app.api.v1.requests.pipeline_runner import pipeline_runner

router = APIRouter(prefix="/metrics", tags=["system"])


@router.get(
    "",
    summary="Get system observability metrics per §34",
)
def get_metrics() -> dict[str, Any]:
    """Return metrics from app.observability.metrics_endpoint including pipeline runner stats."""
    runs = pipeline_runner.get_runs_count()
    avg_duration = pipeline_runner.get_avg_duration()

    try:
        from app.observability.metrics_endpoint import (  # type: ignore
            get_metrics as fetch_metrics,
        )

        if callable(fetch_metrics):
            data = fetch_metrics()
            if isinstance(data, dict):
                data["pipeline_runs"] = runs
                data["avg_duration"] = avg_duration
                data["benchmarks"] = {
                    "max_plan_steps": int(os.getenv("MAX_PLAN_STEPS", 50)),
                    "max_parallel_tool_calls": int(os.getenv("MAX_PARALLEL_TOOL_CALLS", 10)),
                    "target_requests_per_second": 50.0,
                    "vector_search_latency_p99_ms": 15.0,
                    "postgres_query_latency_p99_ms": 5.0,
                    "amqp_message_latency_p99_ms": 2.0,
                    "llm_call_latency_p99_ms": 500.0,
                }
                return data
            return {
                "status": "ok",
                "metrics": data,
                "pipeline_runs": runs,
                "avg_duration": avg_duration,
            }
    except (ImportError, AttributeError, Exception):
        pass

    # §41.13 Benchmarks & Safeguard thresholds
    benchmarks = {
        "max_plan_steps": int(os.getenv("MAX_PLAN_STEPS", 50)),
        "max_parallel_tool_calls": int(os.getenv("MAX_PARALLEL_TOOL_CALLS", 10)),
        "target_requests_per_second": 50.0,
        "vector_search_latency_p99_ms": 15.0,
        "postgres_query_latency_p99_ms": 5.0,
        "amqp_message_latency_p99_ms": 2.0,
        "llm_call_latency_p99_ms": 500.0,
    }

    return {
        "status": "ok",
        "pipeline_runs": runs,
        "avg_duration": avg_duration,
        "benchmarks": benchmarks,
    }
