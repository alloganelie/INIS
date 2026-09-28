"""In-memory registry for the 14 mandatory metrics of §34.

No Prometheus client is required: counters, gauges and histogram samples are
aggregated in memory and exposed either as the historical JSON payload
(``GET /v1/metrics``) or as Prometheus text exposition
(``GET /v1/metrics?format=prometheus``) by
:mod:`app.observability.metrics_endpoint`.

Metric kinds are the ones §34 implies:

* ``counter``   — monotonically increasing totals (``llm_cost``);
* ``gauge``     — instantaneous rates (``request_success_rate``,
  ``cache_hit_rate``…), computed from a success/total outcome tally so a rate
  is never fabricated from a single sample;
* ``histogram`` — sampled distributions exposing ``p50``/``p95``/``p99``
  (``request_latency``, ``confidence_distribution``…). Samples are kept in a
  bounded reservoir (``_MAX_SAMPLES``) so a long-running process cannot grow
  without limit; the aggregation keys (count/sum/avg/min/max) stay available.
"""

from __future__ import annotations

from collections import deque
from typing import Any
from typing import Final
from typing import Literal

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

MetricKind = Literal["counter", "gauge", "histogram"]

#: §34 kind of each mandatory metric.
METRIC_KINDS: dict[str, MetricKind] = {
    "request_success_rate": "gauge",
    "request_latency": "histogram",
    "source_failure_rate": "gauge",
    "tool_failure_rate": "gauge",
    "agent_success_rate": "gauge",
    "confidence_distribution": "histogram",
    "conflict_rate": "gauge",
    "stale_data_rate": "gauge",
    "cache_hit_rate": "gauge",
    "vector_search_latency": "histogram",
    "postgres_latency": "histogram",
    "broker_latency": "histogram",
    "llm_cost": "counter",
    "llm_latency": "histogram",
}

#: Rate gauges whose *bad* event is the interesting one: their value is the
#: failure ratio, not the success ratio.
_FAILURE_RATE_METRICS: Final[frozenset[str]] = frozenset(
    {
        "source_failure_rate",
        "tool_failure_rate",
        "stale_data_rate",
        "conflict_rate",
    }
)
#: Histogram metrics expose these pre-computed quantiles.
QUANTILES: tuple[float, ...] = (0.5, 0.95, 0.99)

#: Upper bound on the sample reservoir kept per histogram metric.
_MAX_SAMPLES: Final[int] = 2000




class MetricsRegistry:
    """Thread-safe-enough in-memory registry (counters, gauges, histograms)."""

    def __init__(self) -> None:
        self._counters: dict[str, float] = {name: 0.0 for name in METRIC_NAMES}
        self._observed_count: dict[str, int] = {name: 0 for name in METRIC_NAMES}
        self._observed_sum: dict[str, float] = {name: 0.0 for name in METRIC_NAMES}
        self._observed_min: dict[str, float | None] = {name: None for name in METRIC_NAMES}
        self._observed_max: dict[str, float | None] = {name: None for name in METRIC_NAMES}
        self._samples: dict[str, deque[float]] = {
            name: deque(maxlen=_MAX_SAMPLES) for name in METRIC_NAMES
        }
        self._gauge_values: dict[str, float | None] = {name: None for name in METRIC_NAMES}
        self._outcome_success: dict[str, int] = {name: 0 for name in METRIC_NAMES}
        self._outcome_total: dict[str, int] = {name: 0 for name in METRIC_NAMES}

    def _check_name(self, name: str) -> None:
        if name not in self._counters:
            raise ValueError(
                f"Unknown metric: {name}. Mandatory metrics: {sorted(self._counters)}"
            )

    # -- counters --------------------------------------------------------

    def increment(self, name: str, amount: int = 1) -> int:
        """Add ``amount`` to a counter; return the new value."""
        self._check_name(name)
        if amount < 0:
            raise ValueError("amount must be >= 0")
        self._counters[name] = float(self._counters[name]) + amount
        return int(self._counters[name])

    def add(self, name: str, amount: float) -> float:
        """Add a fractional ``amount`` (used by the ``llm_cost`` counter)."""
        self._check_name(name)
        if amount < 0:
            raise ValueError("amount must be >= 0")
        self._counters[name] = float(self._counters[name]) + float(amount)
        return float(self._counters[name])

    def counter(self, name: str) -> float:
        """Return the current counter value."""
        self._check_name(name)
        return float(self._counters[name])

    # -- histograms ------------------------------------------------------

    def observe(self, name: str, value: float) -> None:
        """Record one sampled value (latency, confidence score…)."""
        self._check_name(name)
        sample = float(value)
        self._observed_count[name] += 1
        self._observed_sum[name] += sample
        current_min = self._observed_min[name]
        current_max = self._observed_max[name]
        self._observed_min[name] = sample if current_min is None else min(current_min, sample)
        self._observed_max[name] = sample if current_max is None else max(current_max, sample)
        self._samples[name].append(sample)

    def quantiles(self, name: str) -> dict[str, float | None]:
        """Return ``{"p50": …, "p95": …, "p99": …}`` for *name* (§34)."""
        self._check_name(name)
        samples = sorted(self._samples[name])
        return {f"p{int(q * 100)}": _quantile(samples, q) for q in QUANTILES}

    # -- gauges ----------------------------------------------------------

    def set_gauge(self, name: str, value: float | None) -> None:
        """Store an instantaneous value for a gauge metric."""
        self._check_name(name)
        self._gauge_values[name] = None if value is None else float(value)

    def gauge(self, name: str) -> float | None:
        """Return the gauge value, or the rate derived from recorded outcomes."""
        self._check_name(name)
        derived = self._rate(name)
        if derived is not None:
            return derived
        return self._gauge_values[name]

    def record_outcome(self, name: str, failure: bool = False) -> float | None:
        """Record one success/failure outcome and refresh the rate gauge.

        Returns the recomputed rate (``None`` when nothing was recorded yet).
        """
        self._check_name(name)
        self._outcome_total[name] += 1
        if not failure:
            self._outcome_success[name] += 1
        rate = self._rate(name)
        self._gauge_values[name] = rate
        return rate

    def _rate(self, name: str) -> float | None:
        total = self._outcome_total[name]
        if not total:
            return None
        success_ratio = self._outcome_success[name] / total
        if name in _FAILURE_RATE_METRICS:
            return 1.0 - success_ratio
        return success_ratio

    # -- exposition ------------------------------------------------------

    def snapshot(self) -> dict[str, dict[str, float | int | None]]:
        """Return the 14 §34 metrics with counters, rates and quantiles."""
        snapshot: dict[str, dict[str, float | int | None]] = {}
        for name in METRIC_NAMES:
            count = self._observed_count[name]
            total = self._observed_sum[name]
            entry: dict[str, float | int | None] = {
                "kind": METRIC_KINDS[name],
                "count": int(self._counters[name]),
                "observed": count,
                "sum": total,
                "avg": (total / count) if count else None,
                "min": self._observed_min[name],
                "max": self._observed_max[name],
                "gauge": self.gauge(name),
            }
            entry.update(self.quantiles(name))
            snapshot[name] = entry
        return snapshot

    def render_prometheus(self) -> str:
        """Render every metric in the Prometheus text exposition format."""
        lines: list[str] = []
        for name in METRIC_NAMES:
            kind = METRIC_KINDS[name]
            lines.append(f"# HELP {name} INIS §34 mandatory metric {name} ({kind})")
            lines.append(f"# TYPE {name} {kind}")
            if kind == "counter":
                lines.append(f"{name}_total {_fmt(self._counters[name])}")
                continue
            if kind == "gauge":
                lines.append(f"{name} {_fmt(self.gauge(name))}")
                continue
            lines.append(f"{name}_count {self._observed_count[name]}")
            lines.append(f"{name}_sum {_fmt(self._observed_sum[name])}")
            for key, value in self.quantiles(name).items():
                lines.append(f"# TYPE {name}_{key} gauge")
                lines.append(f"{name}_{key} {_fmt(value)}")
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        """Clear every counter, gauge, outcome and sample (tests only)."""
        for name in METRIC_NAMES:
            self._counters[name] = 0.0
            self._observed_count[name] = 0
            self._observed_sum[name] = 0.0
            self._observed_min[name] = None
            self._observed_max[name] = None
            self._samples[name].clear()
            self._gauge_values[name] = None
            self._outcome_success[name] = 0
            self._outcome_total[name] = 0


def _quantile(sorted_samples: list[float], quantile: float) -> float | None:
    """Return the *quantile* of an already sorted sample list (nearest-rank)."""
    if not sorted_samples:
        return None
    if len(sorted_samples) == 1:
        return sorted_samples[0]
    position = quantile * (len(sorted_samples) - 1)
    lower = int(position)
    upper = min(lower + 1, len(sorted_samples) - 1)
    fraction = position - lower
    return sorted_samples[lower] + (sorted_samples[upper] - sorted_samples[lower]) * fraction


def _fmt(value: float | None) -> str:
    """Format a sample for the exposition format (``NaN`` when unknown)."""
    if value is None:
        return "NaN"
    return repr(float(value))



#: Process-wide registry used by the ``/v1/metrics`` endpoint by default.
DEFAULT_REGISTRY = MetricsRegistry()


# -- module-level helpers used by the instrumented modules ----------------


def record_outcome(name: str, failure: bool = False) -> None:
    """Record one success/failure outcome on the process-wide registry."""
    DEFAULT_REGISTRY.record_outcome(name, failure=failure)


def observe_value(name: str, value: float) -> None:
    """Record one observation on the process-wide registry."""
    DEFAULT_REGISTRY.observe(name, value)


def add_cost(amount: float) -> None:
    """Add *amount* to the ``llm_cost`` counter (§34)."""
    DEFAULT_REGISTRY.add("llm_cost", amount)


def set_gauge_value(name: str, value: float | None) -> None:
    """Store a gauge value on the process-wide registry."""
    DEFAULT_REGISTRY.set_gauge(name, value)


def prometheus_text(registry: MetricsRegistry | None = None) -> str:
    """Return the Prometheus exposition of *registry* (default: process-wide)."""
    return (registry or DEFAULT_REGISTRY).render_prometheus()


def snapshot(registry: MetricsRegistry | None = None) -> dict[str, Any]:
    """Return the JSON snapshot of *registry* (default: process-wide)."""
    return (registry or DEFAULT_REGISTRY).snapshot()

#: Histogram metrics expose these pre-computed quantiles.
QUANTILES: tuple[float, ...] = (0.5, 0.95, 0.99)

#: Upper bound on the sample reservoir kept per histogram metric.
_MAX_SAMPLES: Final[int] = 2000
