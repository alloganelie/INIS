"""Metrics router exposing system observability metrics per §32 and §34."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/metrics", tags=["system"])


@router.get(
    "",
    summary="Get system observability metrics per §34",
)
def get_metrics() -> dict[str, Any]:
    """Return metrics from app.observability.metrics_endpoint or not_implemented."""
    try:
        from app.observability.metrics_endpoint import (  # type: ignore
            get_metrics as fetch_metrics,
        )

        if callable(fetch_metrics):
            data = fetch_metrics()
            if isinstance(data, dict):
                return data
            return {"status": "ok", "metrics": data}
    except (ImportError, AttributeError, Exception):
        pass

    return {"status": "not_implemented"}
