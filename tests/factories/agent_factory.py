"""Deterministic §6 agent-identity builders (§6.2, §33.2)."""

from __future__ import annotations

from typing import Any

from app.registry.agent_registry import AgentIdentity

#: The capability every default agent advertises.
DEFAULT_CAPABILITY = "web_search"


def make_agent_identity(
    agent_id: str = "AGENT_TEST",
    **overrides: Any,
) -> AgentIdentity:
    """Return a valid §6.2 :class:`~app.registry.agent_registry.AgentIdentity`.

    Args:
        agent_id: Registry key; must equal the identity's own ``agent_id``
            (``AgentRegistry.register`` refuses a mismatch).
        **overrides: Any identity field, e.g. ``status="degraded"`` or
            ``capabilities=[]`` to build a capability-less agent.
    """
    values: dict[str, Any] = {
        "agent_id": agent_id,
        "name": "Test Agent",
        "description": "Deterministic agent used by the INIS test suite.",
        "version": "1.0.0",
        "status": "available",
        "capabilities": [DEFAULT_CAPABILITY],
        "protocols": ["amqp"],
        "message_types": ["capability_query", "task_assignment"],
        "input_schemas": [],
        "output_schemas": [],
        "security_requirements": [],
        "health": {"healthy": True},
        "performance_profile": {"avg_latency_ms": 10},
        "learning_profile": {"success_rate": 1.0},
    }
    values.update(overrides)
    return AgentIdentity(**values)


def make_agent_identity_dict(agent_id: str = "AGENT_TEST", **overrides: Any) -> dict[str, Any]:
    """Return the ``to_dict`` projection of :func:`make_agent_identity`."""
    return make_agent_identity(agent_id, **overrides).to_dict()

