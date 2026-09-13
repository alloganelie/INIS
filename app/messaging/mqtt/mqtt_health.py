"""MQTT connectivity health check (stub, never raises)."""

from __future__ import annotations

from datetime import datetime
from datetime import timezone
from typing import Any
from typing import Protocol


class _MqttLike(Protocol):
    @property
    def is_connected(self) -> bool: ...


async def health_check(
    client: _MqttLike | None = None,
    host: str = "localhost",
    port: int = 1883,
) -> dict[str, Any]:
    """Return MQTT health without opening any connection.

    Returns:
        Dict with ``status`` (``up`` | ``down`` | ``unknown``),
        ``latency_ms`` (always None for the stub: no I/O probing),
        ``broker``, ``host``, ``port`` and ``checked_at``.
    """
    checked_at = datetime.now(timezone.utc).isoformat()
    if client is None:
        return {
            "status": "unknown",
            "latency_ms": None,
            "broker": "mqtt",
            "host": host,
            "port": port,
            "checked_at": checked_at,
        }
    try:
        connected = bool(client.is_connected)
    except Exception:
        connected = False
    return {
        "status": "up" if connected else "down",
        "latency_ms": None,
        "broker": "mqtt",
        "host": host,
        "port": port,
        "checked_at": checked_at,
    }
