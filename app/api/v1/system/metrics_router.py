"""Metrics router exposing system observability metrics per §32 and §34."""

from __future__ import annotations

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
        "status": "not_implemented",
        "pipeline_runs": runs,
        "avg_duration": avg_duration,
    }
