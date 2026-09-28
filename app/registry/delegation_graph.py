"""Delegation topology: cycle detection and depth limits (§41.10).

Implements the two operations required by the spec::

    DelegationGraph.detect_cycle(path)             -> bool
    DelegationGraph.max_depth_reached(path, depth) -> bool

plus a graph-wide :meth:`DelegationGraph.find_cycle` used to detect and
break delegation loops (INIS → A → B → INIS) *before* the loop closes.
Pure in-memory graph logic, no I/O.
"""

from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Sequence

#: Spec default when no ``max_delegation_depth`` is configured (§41.10).
DEFAULT_MAX_DELEGATION_DEPTH = 5

AgentId = str
Path = Sequence[AgentId]


class DelegationGraph:
    """Directed graph of delegation edges ``from -> to`` between agents."""

    def __init__(self, edges: Iterable[tuple[AgentId, AgentId]] = ()) -> None:
        self._edges: dict[AgentId, set[AgentId]] = {}
        for source, target in edges:
            self.add_delegation(source, target)

    @staticmethod
    def _validate(agent_id: str, label: str) -> None:
        if not agent_id or not isinstance(agent_id, str):
            raise ValueError(f"{label} must be a non-empty string")

    def add_delegation(self, source: AgentId, target: AgentId) -> None:
        """Record that *source* may delegate to *target*."""
        self._validate(source, "source")
        self._validate(target, "target")
        self._edges.setdefault(source, set()).add(target)

    @property
    def edges(self) -> dict[AgentId, frozenset[AgentId]]:
        """Return a read-only copy of the adjacency map."""
        return {agent: frozenset(targets) for agent, targets in self._edges.items()}

    def detect_cycle(self, path: Path) -> bool:
        """Return whether *path* already revisits an agent (§41.10).

        A delegation path where the same agent appears twice closes a
        cycle (``INIS → A → B → INIS``).
        """
        seen: set[AgentId] = set()
        for agent in path:
            if agent in seen:
                return True
            seen.add(agent)
        return False

    def would_create_cycle(self, path: Path, target: AgentId) -> bool:
        """Return whether delegating *path[-1] → target* would close a loop.

        Used **before** appending the next hop so the cycle is broken
        instead of being executed (§41.10: "détecter et rompre").
        """
        self._validate(target, "target")
        if not path:
            return False
        return target in path

    def max_depth_reached(self, path: Path, max_depth: int) -> bool:
        """Return whether *path* has reached *max_depth* delegation hops.

        The depth of ``[A, B, C]`` is 2 (A→B, B→C). Raises:
            ValueError: when ``max_depth`` < 1.
        """
        if max_depth < 1:
            raise ValueError("max_depth must be >= 1")
        if not path:
            return False
        return (len(path) - 1) >= max_depth

    def find_cycle(self) -> list[AgentId] | None:
        """Return one cycle of the graph (its agents), or ``None``.

        Iterative DFS with white/gray/black coloring; a "finish" marker
        keeps a node gray until its whole subtree is explored, and the
        gray stack slice between a repeated node and its second
        occurrence is the cycle.
        """
        color: dict[AgentId, int] = {}
        parent: dict[AgentId, AgentId | None] = {}
        stack: list[tuple[AgentId, AgentId | None, bool]] = [
            (agent, None, False) for agent in sorted(self._edges)
        ]
        while stack:
            agent, from_agent, finishing = stack.pop()
            if finishing:
                color[agent] = 2  # black — subtree done
                continue
            if color.get(agent, 0) != 0:
                continue
            color[agent] = 1  # gray — on the current path
            parent[agent] = from_agent
            stack.append((agent, from_agent, True))
            for target in sorted(self._edges.get(agent, ())):
                state = color.get(target, 0)
                if state == 1:
                    # Reconstruct agent -> ... -> target -> agent
                    cycle = [target]
                    node: AgentId | None = agent
                    while node is not None and node != target:
                        cycle.append(node)
                        node = parent.get(node)
                    cycle.append(target)
                    return list(reversed(cycle))
                if state == 0:
                    stack.append((target, agent, False))
        return None

    def evaluate_delegation(
        self,
        path: Path,
        target: AgentId,
        max_depth: int | None = None,
    ) -> tuple[bool, str]:
        """Decide whether to append *target* to *path* (§41.10 "rompre").

        Returns:
            ``(allowed, reason)`` — ``reason`` explains a refusal in plain
            words (``"cycle"``, ``"max_depth"``, ``"unknown_target"``,
            ``"empty_path"``) or ``"ok"``.

        Raises:
            ValueError: on invalid arguments (empty agents, ``max_depth`` < 1).
        """
        limit = max_depth if max_depth is not None else DEFAULT_MAX_DELEGATION_DEPTH
        if limit < 1:
            raise ValueError("max_depth must be >= 1")
        self._validate(target, "target")
        if not path:
            return False, "empty_path"
        if self.would_create_cycle(path, target):
            return False, "cycle"
        if self.max_depth_reached(path, limit):
            return False, "max_depth"
        if target not in self._edges.get(path[-1], set()):
            return False, "unknown_target"
        return True, "ok"
