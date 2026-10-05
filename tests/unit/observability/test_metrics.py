"""Tests for the in-memory metrics registry per §34."""

import pytest

from app.observability.metrics import METRIC_NAMES, MetricsRegistry
from app.observability.metrics_endpoint import get_metrics


class TestMetrics:
    """5 tests covering counters, observations and exposition."""

    def test_increment_counts_events(self) -> None:
        """increment accumulates and returns the new counter value."""
        registry = MetricsRegistry()

        assert registry.increment("request_latency") == 1
        assert registry.increment("request_latency", 4) == 5
        assert registry.snapshot()["request_latency"]["count"] == 5

    def test_observe_aggregates_without_storing_samples(self) -> None:
        """observe maintains count/sum/avg/min/max online."""
        registry = MetricsRegistry()
        registry.observe("llm_latency", 100.0)
        registry.observe("llm_latency", 300.0)

        entry = registry.snapshot()["llm_latency"]

        assert entry["observed"] == 2
        assert entry["sum"] == 400.0
        assert entry["avg"] == 200.0
        assert entry["min"] == 100.0
        assert entry["max"] == 300.0

    def test_snapshot_exposes_all_mandatory_metrics(self) -> None:
        """snapshot always contains the 14 §34 metric names."""
        snapshot = MetricsRegistry().snapshot()

        assert set(snapshot) == set(METRIC_NAMES)
        assert len(snapshot) == 14

    def test_unknown_metric_raises(self) -> None:
        """increment/observe reject names outside §34 explicitly."""
        registry = MetricsRegistry()

        with pytest.raises(ValueError, match="Unknown metric"):
            registry.increment("nosuch_metric")
        with pytest.raises(ValueError, match="Unknown metric"):
            registry.observe("nosuch_metric", 1.0)

    def test_get_metrics_exposes_registry_snapshot(self) -> None:
        """get_metrics wraps the snapshot with service metadata."""
        registry = MetricsRegistry()
        registry.increment("llm_cost", 3)

        payload = get_metrics(registry)

        assert payload["service"] == "inis"
        assert "generated_at" in payload
        assert payload["metrics"]["llm_cost"]["count"] == 3


class TestBenchmarkThresholds:
    """§41.13 — the eight benchmarks are exposed under ``/v1/metrics → benchmarks``.

    They are *thresholds* (configuration + deployment targets), never measured
    results. §41.13 names exactly eight; none may stay in an unreachable zone.
    """

    #: §41.13 names → whether the exposed value is a count (int) or a target (float).
    EXPECTED_NAMES = (
        ("max_plan_steps", int),
        ("max_parallel_tool_calls", int),
        ("max_information_units_per_request", int),
        ("target_requests_per_second", float),
        ("vector_search_latency_p99_ms", float),
        ("postgres_query_latency_p99_ms", float),
        ("amqp_message_latency_p99_ms", float),
        ("llm_call_latency_p99_ms", float),
    )

    def test_the_eight_names_are_exposed_with_the_right_kind(self) -> None:
        from app.api.v1.system.metrics_router import _benchmarks

        benchmarks = _benchmarks()
        expected = dict(self.EXPECTED_NAMES)

        assert set(benchmarks) == set(expected), "§41.13 names eight benchmarks, no more, no less"
        for name, kind in expected.items():
            assert isinstance(benchmarks[name], kind), f"{name} should be a {kind.__name__}"
        assert benchmarks["max_information_units_per_request"] > 0
        assert benchmarks["max_plan_steps"] > 0
        assert benchmarks["max_parallel_tool_calls"] > 0

