"""Deterministic §7 request builders (§7, §33.2)."""

from __future__ import annotations

from typing import Any

#: The objective every default request asks for.
DEFAULT_OBJECTIVE = "Quelle est la capitale de la France ?"


def make_request_payload(**overrides: Any) -> dict[str, Any]:
    """Return a ``POST /v1/requests`` payload (§7 ``InformationRequestCreate``).

    Args:
        **overrides: Any field of the §7 wire schema, e.g.
            ``minimum_confidence`` inside ``constraints`` to drive a §8.5 stop
            condition, or ``request_type="artifact"`` for a §24 request.

    Returns:
        A payload with the documented §7 defaults (``research``,
        ``minimum_confidence`` 0.5, 900 s TTL).
    """
    payload: dict[str, Any] = {
        "objective": DEFAULT_OBJECTIVE,
        "request_type": "research",
        "question": DEFAULT_OBJECTIVE,
        "context": {"working_language": "fr"},
        "required_information": ["capital of France"],
        "constraints": {
            "source_preferences": [],
            "minimum_confidence": 0.5,
            "maximum_execution_time_seconds": 60,
            "maximum_iterations": 3,
            "maximum_web_depth": 2,
        },
        "required_output": {"format": "json", "fields": ["answer", "sources"]},
        "requester": {"type": "agent", "id": "AGENT_TEST"},
        "permissions": {"scope": "read"},
        "ttl_seconds": 900,
    }
    constraints = overrides.pop("constraints", None)
    payload.update(overrides)
    if constraints is not None:
        merged = dict(payload["constraints"])
        merged.update(constraints)
        payload["constraints"] = merged
    return payload

