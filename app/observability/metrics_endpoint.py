"""Metrics exposition for ``GET /v1/metrics`` (pure dict, no HTTP here).

The API zone (Antigravity) serves the returned dict as JSON; this
module only builds it from a :class:`MetricsRegistry` snapshot.
"""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import Any

from app.observability.metrics import DEFAULT_REGISTRY
from app.observability.metrics import MetricsRegistry


def get_metrics(registry: MetricsRegistry | None = None) -> dict[str, Any]:
    """Return the metrics payload (all 14 §34 metrics + metadata)."""
    active = registry or DEFAULT_REGISTRY
    return {
        "service": "inis",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": active.snapshot(),
    }
