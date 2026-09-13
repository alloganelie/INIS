"""AMQP connectivity health check (never raises, never blocks workers)."""

from __future__ import annotations

import time
from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Protocol

from app.messaging.amqp.topology import MAIN_QUEUE


class _BrokerLike(Protocol):
    @property
    def is_connected(self) -> bool: ...


async def health_check(
    broker: _BrokerLike | None = None,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    """Check RabbitMQ reachability and return a status dict.

    Args:
        broker: Optional broker exposing ``is_connected``. When None,
            the check reports ``unknown`` without any I/O.
        timeout_seconds: Reserved for future active probing (unused
            without a live broker to avoid blocking).

    Returns:
        Dict with ``status`` (``up`` | ``down`` | ``unknown``),
        ``latency_ms``, ``broker``, ``queue`` and ``checked_at``.
    """
    _ = timeout_seconds
    started = time.perf_counter()
    checked_at = datetime.now(timezone.utc).isoformat()
    if broker is None:
        return {
            "status": "unknown",
            "latency_ms": None,
            "broker": "amqp",
            "queue": MAIN_QUEUE,
            "checked_at": checked_at,
        }
    try:
        connected = bool(broker.is_connected)
    except Exception:
        connected = False
    latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
    return {
        "status": "up" if connected else "down",
        "latency_ms": latency_ms,
        "broker": "amqp",
        "queue": MAIN_QUEUE,
        "checked_at": checked_at,
    }
