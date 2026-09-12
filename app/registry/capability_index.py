"""Capability index for agent discovery per §6."""

from collections import defaultdict
from typing import Any


class CapabilityIndex:
    """Index mapping capability -> set of agent_ids."""

    def __init__(self) -> None:
        self._index: dict[str, set[str]] = defaultdict(set)
        self._agent_capabilities: dict[str, set[str]] = defaultdict(set)

    def add_agent(self, agent_id: str, capabilities: list[str]) -> None:
        """Add agent capabilities to index."""
        for capability in capabilities:
            self._index[capability].add(agent_id)
            self._agent_capabilities[agent_id].add(capability)

    def remove_agent(self, agent_id: str) -> None:
        """Remove agent from index."""
        capabilities = self._agent_capabilities.pop(agent_id, set())
        for capability in capabilities:
            self._index[capability].discard(agent_id)
            if not self._index[capability]:
                del self._index[capability]

    def update_agent(self, agent_id: str, new_capabilities: list[str]) -> None:
        """Update agent capabilities in index."""
        self.remove_agent(agent_id)
        self.add_agent(agent_id, new_capabilities)

    def get_agents_for_capability(self, capability: str) -> list[str]:
        """Get all agent_ids that have the given capability."""
        return list(self._index.get(capability, set()))

    def get_capabilities_for_agent(self, agent_id: str) -> list[str]:
        """Get all capabilities for a given agent."""
        return list(self._agent_capabilities.get(agent_id, set()))

    def has_capability(self, capability: str) -> bool:
        """Check if any agent has the given capability."""
        return capability in self._index

    def list_capabilities(self) -> list[str]:
        """List all indexed capabilities."""
        return list(self._index.keys())

    def to_dict(self) -> dict[str, list[str]]:
        """Export index as dictionary."""
        return {cap: list(agents) for cap, agents in self._index.items()}

    @classmethod
    def from_dict(cls, data: dict[str, list[str]]) -> "CapabilityIndex":
        """Create CapabilityIndex from dictionary."""
        index = cls()
        for capability, agent_ids in data.items():
            for agent_id in agent_ids:
                index._index[capability].add(agent_id)
                index._agent_capabilities[agent_id].add(capability)
        return index