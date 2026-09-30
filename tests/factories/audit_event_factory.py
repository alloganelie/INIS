"""Deterministic §20.1 audit-event builders (§20.1, §33.2)."""

from __future__ import annotations

from typing import Any

from app.domain.value_objects.ulid import ULID

#: The action every default event records.
DEFAULT_ACTION = "source.read"


def make_audit_event(**overrides: Any) -> dict[str, Any]:
    """Return an audit-event payload carrying every §20.1 required field.

    ``AuditWriter.write`` generates ``audit_event_id``/timestamps itself, so the
    factory deliberately omits them: a test that wants to assert on generated
    metadata must not be able to pre-seed it.

    Args:
        **overrides: Any field of the §20.1 contract, e.g.
            ``result="failure", reason="access denied"`` for a §19.2 denial.
    """
    values: dict[str, Any] = {
        "actor_type": "agent",
        "actor_id": "AGENT_TEST",
        "action": DEFAULT_ACTION,
        "resource_type": "source",
        "resource_id": ULID.new("SRC_"),
        "request_id": ULID.new("REQ_"),
        "result": "success",
        "reason": "granted by policy",
    }
    values.update(overrides)
    return values

