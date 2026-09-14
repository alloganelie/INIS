"""Distributed tracing over OpenTelemetry (§20.2, never blocking).

``TraceContext`` carries trace_id (32 hex), span_id (16 hex),
correlation_id and causation_id on every request. Backend wiring is
lazy: ``configure_tracing`` installs a real SDK provider when
``opentelemetry-sdk`` is installed, otherwise reports a ``noop``
backend (only the API is required here). ``get_tracer`` always
returns a tracer exposing ``start_span(name)`` as a context manager,
so callers never branch on backend availability.
"""

from __future__ import annotations

import re
import secrets
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any
from typing import Iterator

_TRACE_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SPAN_ID_RE = re.compile(r"^[0-9a-f]{16}$")


@dataclass(frozen=True)
class TraceContext:
    """Validated trace propagation context (§20.2)."""

    trace_id: str
    span_id: str
    correlation_id: str
    causation_id: str | None = None

    def __post_init__(self) -> None:
        if not _TRACE_ID_RE.match(self.trace_id or ""):
            raise ValueError("trace_id must be a 32-char lowercase hex string")
        if not _SPAN_ID_RE.match(self.span_id or ""):
            raise ValueError("span_id must be a 16-char lowercase hex string")
        if not self.correlation_id or not isinstance(self.correlation_id, str):
            raise ValueError("correlation_id must be a non-empty string")
        if self.causation_id is not None and not isinstance(self.causation_id, str):
            raise ValueError("causation_id must be a string or None")

    @classmethod
    def new(cls, correlation_id: str, causation_id: str | None = None) -> "TraceContext":
        """Create a root context with fresh trace and span ids."""
        return cls(
            trace_id=secrets.token_hex(16),
            span_id=secrets.token_hex(8),
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    def child_span(self) -> "TraceContext":
        """Derive a child context (same trace, fresh span)."""
        return TraceContext(
            trace_id=self.trace_id,
            span_id=secrets.token_hex(8),
            correlation_id=self.correlation_id,
            causation_id=self.causation_id,
        )


class _NoopSpan:
    def __init__(self, name: str) -> None:
        self.name = name

    def set_attribute(self, key: str, value: Any) -> None:
        """Noop: record nothing."""

    def __enter__(self) -> "_NoopSpan":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _NoopTracer:
    def __init__(self, name: str) -> None:
        self.name = name

    @contextmanager
    def start_span(self, name: str) -> Iterator[_NoopSpan]:
        """Yield a noop span (backend unavailable)."""
        yield _NoopSpan(name)


class _OtelTracer:
    def __init__(self, name: str, otel_tracer: Any) -> None:
        self.name = name
        self._otel_tracer = otel_tracer

    @contextmanager
    def start_span(self, name: str) -> Iterator[Any]:
        """Delegate to ``start_as_current_span`` (SDK or noop API)."""
        with self._otel_tracer.start_as_current_span(name) as span:
            yield span


def configure_tracing(service_name: str = "inis") -> dict[str, Any]:
    """Install the SDK tracer provider when available; never raises.

    Returns ``{"backend": "otel"|"noop", ...}`` describing the active
    backend. Without ``opentelemetry-sdk`` the API alone is used and
    spans are valid but not exported.
    """
    try:
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry import trace as trace_api

        provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
        trace_api.set_tracer_provider(provider)
        return {"backend": "otel", "service_name": service_name}
    except Exception as exc:
        return {
            "backend": "noop",
            "service_name": service_name,
            "reason": f"{type(exc).__name__}: {exc}",
        }


def get_tracer(name: str) -> _OtelTracer | _NoopTracer:
    """Return a tracer with a ``start_span(name)`` context manager."""
    if not name or not isinstance(name, str):
        raise ValueError("name must be a non-empty string")
    try:
        from opentelemetry import trace as trace_api

        return _OtelTracer(name, trace_api.get_tracer(name))
    except Exception:
        return _NoopTracer(name)
