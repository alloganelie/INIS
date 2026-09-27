"""Inter-agent trust topology (§41.10 ``agent_trust_graph`` ``[CONFIG]``).

The graph maps each agent to the agents it may delegate to, the trust
level of that relationship (``full | partial | minimal``) and the maximum
delegation depth it accepts. :func:`can_delegate` combines the trust
graph with the :class:`~app.registry.delegation_graph.DelegationGraph`
so a delegation step is allowed only when the target is trusted **and**
the step neither closes a cycle nor exceeds the depth limit (§41.10).
"""

from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from typing import Any

from app.domain.enums.delegation_effect import DelegationEffect
from app.domain.enums.trust_level import TrustLevel
from app.registry.delegation_graph import DelegationGraph

#: Shape of one ``agent_trust_graph`` entry (§41.10).
TRUST_ENTRY_KEYS = frozenset({"trusted_agents", "trust_level", "max_delegation_depth"})


def _coerce_trust_level(value: Any) -> TrustLevel:
    if isinstance(value, TrustLevel):
        return value
    try:
        return TrustLevel(str(value))
    except ValueError:
        allowed = [level.value for level in TrustLevel]
        raise ValueError(
            f"trust_level must be one of {allowed}, got {value!r}"
        ) from None


class TrustGraph:
    """Known topology of trust relations between agents (§41.10)."""

    def __init__(
        self, config: Mapping[str, Mapping[str, Any]] | None = None
    ) -> None:
        self._entries: dict[str, dict[str, Any]] = {}
        if config:
            for agent_id, entry in config.items():
                if not isinstance(entry, Mapping):
                    raise ValueError(f"entry for {agent_id!r} must be a mapping")
                missing = sorted(TRUST_ENTRY_KEYS - set(entry))
                if missing:
                    raise ValueError(
                        f"entry for {agent_id!r} is missing keys: {missing}"
                    )
                self.set_entry(
                    agent_id,
                    trusted_agents=entry["trusted_agents"],
                    trust_level=entry["trust_level"],
                    max_delegation_depth=entry["max_delegation_depth"],
                )

    def set_entry(
        self,
        agent_id: str,
        *,
        trusted_agents: Sequence[str],
        trust_level: Any,
        max_delegation_depth: int,
    ) -> None:
        """Register (or replace) the trust entry of *agent_id*."""
        if not agent_id or not isinstance(agent_id, str):
            raise ValueError("agent_id must be a non-empty string")
        if isinstance(trusted_agents, str) or not isinstance(
            trusted_agents, Sequence
        ):
            raise ValueError("trusted_agents must be a sequence of agent ids")
        cleaned: list[str] = []
        for trusted in trusted_agents:
            if not trusted or not isinstance(trusted, str):
                raise ValueError("trusted_agents entries must be non-empty strings")
            cleaned.append(trusted)
        if max_delegation_depth < 1:
            raise ValueError("max_delegation_depth must be >= 1")
        self._entries[agent_id] = {
            "trusted_agents": cleaned,
            "trust_level": _coerce_trust_level(trust_level).value,
            "max_delegation_depth": int(max_delegation_depth),
        }

    def _entry(self, agent_id: str) -> dict[str, Any]:
        try:
            return self._entries[agent_id]
        except KeyError:
            raise ValueError(f"Unknown agent in trust graph: {agent_id!r}") from None

    @property
    def agent_ids(self) -> frozenset[str]:
        """Agents known to the trust graph."""
        return frozenset(self._entries)

    def is_trusted(self, source: str, target: str) -> bool:
        """Return whether *source* explicitly trusts *target*."""
        entry = self._entries.get(source)
        return entry is not None and target in entry["trusted_agents"]

    def trust_level(self, agent_id: str) -> TrustLevel:
        """Return the configured trust level of *agent_id*."""
        return TrustLevel(self._entry(agent_id)["trust_level"])

    def max_delegation_depth(self, agent_id: str) -> int:
        """Return the configured maximum delegation depth of *agent_id*."""
        return int(self._entry(agent_id)["max_delegation_depth"])

    def to_dict(self) -> dict[str, Any]:
        """Return the exact §41.10 ``agent_trust_graph`` ``[CONFIG]`` block."""
        return {
            "agent_trust_graph": {
                agent_id: dict(entry)
                for agent_id, entry in sorted(self._entries.items())
            }
        }

    def to_delegation_graph(self) -> DelegationGraph:
        """Materialize the trust relations as delegation edges."""
        graph = DelegationGraph()
        for agent_id, entry in self._entries.items():
            for trusted in entry["trusted_agents"]:
                graph.add_delegation(agent_id, trusted)
        return graph


def can_delegate(
    trust: TrustGraph,
    delegation: DelegationGraph,
    path: Sequence[str],
    target: str,
    *,
    max_depth: int | None = None,
) -> tuple[DelegationEffect, str]:
    """Evaluate one delegation step against trust and topology (§41.10).

    When *max_depth* is not given, the limit configured for the **root**
    agent of *path* applies to the whole chain (``path[0]``); unknown
    roots fall back to the §41.10 default.

    Returns:
        ``(effect, reason)`` — ``allow``/``deny`` plus a plain-word reason
        (``ok``, ``cycle``, ``max_depth``, ``unknown_target``,
        ``empty_path``, ``untrusted_target``, ``unknown_source``).

    Raises:
        ValueError: on invalid arguments (empty agents, ``max_depth`` < 1).
    """
    if not path:
        return DelegationEffect.DENY, "empty_path"
    source = path[-1]
    if source not in trust.agent_ids:
        # Fail closed: an agent absent from the topology may not delegate.
        return DelegationEffect.DENY, "unknown_source"
    depth = max_depth
    if depth is None and path[0] in trust.agent_ids:
        depth = trust.max_delegation_depth(path[0])
    allowed, reason = delegation.evaluate_delegation(path, target, depth)
    if not allowed:
        return DelegationEffect.DENY, reason
    if not trust.is_trusted(source, target):
        return DelegationEffect.DENY, "untrusted_target"
    return DelegationEffect.ALLOW, "ok"

