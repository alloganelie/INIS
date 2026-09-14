"""Tests for TraceContext and tracer wiring per §20.2 (no backend needed)."""

import pytest

from app.observability.tracing import configure_tracing
from app.observability.tracing import get_tracer
from app.observability.tracing import TraceContext


class TestTracing:
    """3 tests covering context validation, configuration and spans."""

    def test_trace_context_validates_ids(self) -> None:
        """trace_id/span_id must be 32/16 lowercase hex."""
        valid = TraceContext(
            trace_id="a" * 32,
            span_id="b" * 16,
            correlation_id="CORR_01",
        )
        assert valid.trace_id == "a" * 32

        child = valid.child_span()
        assert child.trace_id == valid.trace_id
        assert child.span_id != valid.span_id

        with pytest.raises(ValueError, match="trace_id"):
            TraceContext(trace_id="short", span_id="b" * 16, correlation_id="CORR_01")
        with pytest.raises(ValueError, match="span_id"):
            TraceContext(trace_id="a" * 32, span_id="xyz", correlation_id="CORR_01")

    def test_configure_tracing_never_raises(self) -> None:
        """configure_tracing reports noop without the SDK installed."""
        report = configure_tracing()

        assert report["backend"] in ("otel", "noop")
        assert report["service_name"] == "inis"

    def test_tracer_span_is_usable(self) -> None:
        """get_tracer exposes a start_span context manager."""
        tracer = get_tracer("test")

        with tracer.start_span("operation") as span:
            span.set_attribute("key", "value")

        assert tracer.name == "test"
