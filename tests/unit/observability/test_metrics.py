"""Tests for the in-memory metrics registry per §34."""

import pytest

from app.observability.metrics import METRIC_NAMES
from app.observability.metrics import MetricsRegistry
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
