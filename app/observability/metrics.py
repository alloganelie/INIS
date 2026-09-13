"""In-memory metrics registry for the 14 mandatory metrics (§34).

No Prometheus client here: counters and observations are aggregated in
memory and exposed via :func:`snapshot`. The HTTP layer
(``/v1/metrics``, owned by the API zone) reads
:mod:`app.observability.metrics_endpoint`.
"""

from __future__ import annotations

#: The 14 mandatory metric names, exactly as listed in §34.
METRIC_NAMES: tuple[str, ...] = (
    "request_success_rate",
    "request_latency",
    "source_failure_rate",
    "tool_failure_rate",
    "agent_success_rate",
    "confidence_distribution",
    "conflict_rate",
    "stale_data_rate",
    "cache_hit_rate",
    "vector_search_latency",
    "postgres_latency",
    "broker_latency",
    "llm_cost",
    "llm_latency",
)


class MetricsRegistry:
    """Thread-safe-enough in-memory registry (counters + observations).

    - :meth:`increment` counts events (e.g. requests, failures, cost units).
    - :meth:`observe` aggregates sampled values (latencies, scores) as
      running count/sum/min/max — the raw samples are never stored.
    """

    def __init__(self) -> None:
        self._counters: dict[str, int] = {name: 0 for name in METRIC_NAMES}
        self._observed_count: dict[str, int] = {name: 0 for name in METRIC_NAMES}
        self._observed_sum: dict[str, float] = {name: 0.0 for name in METRIC_NAMES}
        self._observed_min: dict[str, float | None] = {name: None for name in METRIC_NAMES}
        self._observed_max: dict[str, float | None] = {name: None for name in METRIC_NAMES}

    def _check_name(self, name: str) -> None:
        if name not in self._counters:
            raise ValueError(
                f"Unknown metric: {name}. Mandatory metrics: {sorted(self._counters)}"
            )

    def increment(self, name: str, amount: int = 1) -> int:
        """Add ``amount`` to a counter; return the new value."""
        self._check_name(name)
        if amount < 0:
            raise ValueError("amount must be >= 0")
        self._counters[name] += amount
        return self._counters[name]

    def observe(self, name: str, value: float) -> None:
        """Record one sampled value (latency, rate component, cost…)."""
        self._check_name(name)
        sample = float(value)
        self._observed_count[name] += 1
        self._observed_sum[name] += sample
        current_min = self._observed_min[name]
        current_max = self._observed_max[name]
        self._observed_min[name] = sample if current_min is None else min(current_min, sample)
        self._observed_max[name] = sample if current_max is None else max(current_max, sample)

    def snapshot(self) -> dict[str, dict[str, float | int | None]]:
        """Return all 14 metrics with counters and observation summaries."""
        snapshot: dict[str, dict[str, float | int | None]] = {}
        for name in METRIC_NAMES:
            count = self._observed_count[name]
            total = self._observed_sum[name]
            snapshot[name] = {
                "count": self._counters[name],
                "observed": count,
                "sum": total,
                "avg": (total / count) if count else None,
                "min": self._observed_min[name],
                "max": self._observed_max[name],
            }
        return snapshot

    def reset(self) -> None:
        """Clear all counters and observations (tests only)."""
        for name in METRIC_NAMES:
            self._counters[name] = 0
            self._observed_count[name] = 0
            self._observed_sum[name] = 0.0
            self._observed_min[name] = None
            self._observed_max[name] = None


#: Process-wide registry used by the ``/v1/metrics`` endpoint by default.
DEFAULT_REGISTRY = MetricsRegistry()
