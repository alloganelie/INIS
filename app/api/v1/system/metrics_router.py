"""Metrics router exposing system observability metrics per §32 and §34."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from app.api.v1.requests.pipeline_runner import pipeline_runner

router = APIRouter(prefix="/metrics", tags=["system"])


def _benchmarks() -> dict[str, float]:
    """Return the §41.13 safeguard thresholds and alert targets."""
    from app.planning.limits import max_parallel_tool_calls, max_plan_steps

    return {
        "max_plan_steps": max_plan_steps(),
        "max_parallel_tool_calls": max_parallel_tool_calls(),
        "target_requests_per_second": 50.0,
        "vector_search_latency_p99_ms": 15.0,
        "postgres_query_latency_p99_ms": 5.0,
        "amqp_message_latency_p99_ms": 2.0,
        "llm_call_latency_p99_ms": 500.0,
    }


@router.get(
    "",
    summary="Get system observability metrics per §34",
)
def get_metrics(
    format: str = Query(
        "json",
        description="Exposition format: 'json' (default) or 'prometheus'.",
    ),
) -> Any:
    """Return the 14 §34 metrics plus pipeline runner stats.

    ``?format=prometheus`` serves the Prometheus text exposition format;
    the default JSON payload is kept unchanged for existing consumers.
    """
    if format.lower() in {"prometheus", "text", "openmetrics"}:
        from app.observability.metrics_endpoint import get_prometheus_metrics

        return PlainTextResponse(
            content=get_prometheus_metrics(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

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
                data["benchmarks"] = _benchmarks()
                return data
            return {
                "status": "ok",
                "metrics": data,
                "pipeline_runs": runs,
                "avg_duration": avg_duration,
            }
    except (ImportError, AttributeError, Exception):
        pass

    return {
        "status": "ok",
        "pipeline_runs": runs,
        "avg_duration": avg_duration,
        "benchmarks": _benchmarks(),
    }

