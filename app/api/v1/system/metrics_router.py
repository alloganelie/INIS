"""Metrics router exposing system observability metrics per §32 and §34."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from app.api.v1.requests.pipeline_runner import pipeline_runner
from app.observability.metrics_endpoint import get_metrics as fetch_metrics

router = APIRouter(prefix="/metrics", tags=["system"])


def _benchmarks() -> dict[str, float | int]:
    """Return the §41.13 safeguard thresholds and alert targets.

    §41.13 names **eight** benchmarks and says they must be exposed in
    ``/v1/metrics``. The eight values below are the repository's own: the two
    guards and the ADR 007 ceiling come from their modules, the five alert
    targets are the documented deployment values. Nothing here is a measured
    result — these are the *thresholds* a campaign compares against.
    """
    from app.knowledge.normalization.limits import max_information_units_per_request
    from app.planning.limits import max_parallel_tool_calls, max_plan_steps

    return {
        "max_plan_steps": max_plan_steps(),
        "max_parallel_tool_calls": max_parallel_tool_calls(),
        "max_information_units_per_request": max_information_units_per_request(),
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

    data = fetch_metrics()
    data["pipeline_runs"] = runs
    data["avg_duration"] = avg_duration
    data["benchmarks"] = _benchmarks()
    return data


