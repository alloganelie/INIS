"""Metrics exposition for ``GET /v1/metrics`` (pure dict, no HTTP here).

The API zone (Antigravity) serves the returned dict as JSON; this
module only builds it from a :class:`MetricsRegistry` snapshot.
"""

from __future__ import annotations

from typing import Any

from app.core.time import utc_now
from app.observability.metrics import DEFAULT_REGISTRY, MetricsRegistry


def get_metrics(registry: MetricsRegistry | None = None) -> dict[str, Any]:
    """Return the metrics payload (all 14 §34 metrics + metadata)."""
    active = registry or DEFAULT_REGISTRY
    return {
        "service": "inis",
        "generated_at": utc_now().isoformat(),
        "metrics": active.snapshot(),
    }


def get_prometheus_metrics(registry: MetricsRegistry | None = None) -> str:
    """Return the 14 §34 metrics in the Prometheus text exposition format."""
    active = registry or DEFAULT_REGISTRY
    return active.render_prometheus()
