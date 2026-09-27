"""§33.3 scenario 6 — « agent externe indisponible ».

When the external agent is gone the tools report absence explicitly: discovery
returns nobody (registry reachable but no match) and transport failures raise
``InfrastructureError`` — never a fabricated envelope (§0.2, §6, §5).
"""

from __future__ import annotations

import pytest

from app.core.errors import InfrastructureError
from app.registry import AgentIdentity, AgentRegistry
from app.tools.agent_tools import (
    InProcessAgentChannel,
    discover_agents,
    receive_agent_result,
    send_agent_request,
)


def _identity(agent_id: str, capabilities: list[str]) -> AgentIdentity:
    return AgentIdentity(
        agent_id=agent_id,
        name=agent_id,
        description="test agent",
        version="1.0.0",
        status="available",
        capabilities=capabilities,
        protocols=["inis/1"],
        message_types=["INFORMATION_REQUEST"],
        input_schemas=[],
        output_schemas=[],
        security_requirements=[],
        health={},
        performance_profile={},
        learning_profile={},
    )


def _envelope() -> dict:
    correlation_id = "CORR_01J00000000000000000000000"
    return {
        "protocol_version": "1.0",
        "message_id": "MSG_01J00000000000000000000000",
        "correlation_id": correlation_id,
        "timestamp": "2026-01-01T00:00:00Z",
        "sender": {"agent_id": "agt_planner", "agent_version": "1.0.0"},
        "recipient": {"agent_id": "agt_gone", "agent_version": "1.0.0"},
        "message_type": "INFORMATION_REQUEST",
        "priority": "normal",
        "ttl_seconds": 60,
        "payload": {},
        "security": {"auth_method": "mtls"},
        "trace": {
            "trace_id": "0" * 32,
            "span_id": "0" * 16,
            "correlation_id": correlation_id,
        },
    }


@pytest.mark.asyncio
async def test_discovery_of_absent_capability_returns_no_agent() -> None:
    """Registry reachable but nobody offers the capability → empty, honestly."""
    registry = AgentRegistry()
    registry.register("agt_a", _identity("agt_a", ["fetch"]))
    assert await discover_agents("summarize", registry=registry) == []


@pytest.mark.asyncio
async def test_send_to_unresponsive_agent_raises_instead_of_faking() -> None:
    """Transport failure while sending surfaces as InfrastructureError."""
    class DeadChannel:
        async def deliver(self, agent_id: str, envelope: dict) -> None:
            raise ConnectionError("agent unreachable")

        async def fetch(self, correlation_id: str) -> dict | None:
            return None

    with pytest.raises(InfrastructureError, match="unreachable"):
        await send_agent_request("agt_gone", _envelope(), channel=DeadChannel())


@pytest.mark.asyncio
async def test_awaiting_result_from_dead_agent_reports_absence() -> None:
    """No deposited result → explicit failure, never an empty envelope."""
    with pytest.raises(InfrastructureError):
        await receive_agent_result(
            "CORR_01J00000000000000000000000", channel=InProcessAgentChannel()
        )
