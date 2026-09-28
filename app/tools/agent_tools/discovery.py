"""``discover_agents`` and ``query_agent_capabilities`` internal tools per §21.

Both tools are thin façades over the §6 registry: they answer "who can do this?"
and "what can this agent do?" without keeping a second copy of the capability
data. When no registry is available the tool raises instead of returning an
empty list, because "no registry" and "no matching agent" are different facts
(§0.2).
"""

from __future__ import annotations

from app.core.errors import InfrastructureError, ValidationError
from app.registry.agent_registry import AgentIdentity, AgentRegistry
from app.registry.capability_index import CapabilityIndex

__all__ = ["discover_agents", "query_agent_capabilities"]


def _require_registry(
    registry: AgentRegistry | None,
    capability_index: CapabilityIndex | None,
    component: str,
) -> AgentRegistry:
    """Return the registry, raising when only an index (no identities) exists."""
    if registry is None:
        raise InfrastructureError(
            f"{component} requires an agent registry (§6) to resolve identities"
        )
    return registry


async def discover_agents(
    capability: str,
    *,
    registry: AgentRegistry | None = None,
    capability_index: CapabilityIndex | None = None,
) -> list[AgentIdentity]:
    """Return the registered agents exposing *capability* (§21).

    Args:
        capability: Capability name to look up, case-sensitive (§6).
        registry: Agent registry holding the identities. When omitted but an
            index is supplied, the tool refuses: the index only knows ids, and
            inventing an identity card for an id would violate §0.2.
        capability_index: Optional §6 capability index used to narrow the scan
            before verifying against the registry.

    Returns:
        The matching agent identities, ordered by ``agent_id`` for stability.

    Raises:
        ValidationError: If *capability* is empty.
        InfrastructureError: If no registry is available.
    """
    if not capability or not str(capability).strip():
        raise ValidationError("capability is required to discover agents (§6)")
    active_registry = _require_registry(registry, capability_index, "discover_agents")

    if capability_index is not None:
        candidate_ids = set(capability_index.get_agents_for_capability(capability))
        matches = [
            agent
            for agent in active_registry.list_agents()
            if agent.agent_id in candidate_ids
        ]
    else:
        matches = [
            agent
            for agent in active_registry.list_agents()
            if capability in agent.capabilities
        ]
    return sorted(matches, key=lambda agent: agent.agent_id)


async def query_agent_capabilities(
    agent_id: str,
    *,
    registry: AgentRegistry | None = None,
) -> list[str]:
    """Return the capability list registered for *agent_id* (§21).

    Args:
        agent_id: Identifier of the agent to query.
        registry: Agent registry holding the identity.

    Returns:
        The agent's capabilities, sorted for stable comparison.

    Raises:
        ValidationError: If *agent_id* is empty.
        InfrastructureError: If no registry is available.
        AgentNotFoundError: If the agent is not registered.
    """
    if not agent_id or not str(agent_id).strip():
        raise ValidationError("agent_id is required to query capabilities (§6)")
    active_registry = _require_registry(registry, None, "query_agent_capabilities")
    identity = active_registry.get(agent_id)
    return sorted(identity.capabilities)
