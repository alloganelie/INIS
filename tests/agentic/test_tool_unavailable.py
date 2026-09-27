"""§33.3 scenario 5 — « outil indisponible ».

An unavailable tool must surface as an explicit failure the planner can react
to — never as a silent empty result (§0.2, §21).
"""

from __future__ import annotations

import pytest

from app.core.errors import InfrastructureError
from app.tools.registry import ToolRegistry


def test_unregistered_tool_is_not_silently_executable() -> None:
    """Asking for a tool that is not registered fails loudly (§21)."""
    registry = ToolRegistry()
    with pytest.raises(KeyError):
        registry.get("read_csv")
    assert registry.list() == []


@pytest.mark.asyncio
async def test_failing_tool_propagates_infrastructure_error() -> None:
    """A tool outage reaches the planner as InfrastructureError, not []."""
    registry = ToolRegistry()

    async def broken_tool(query: str, limit: int):
        raise InfrastructureError("search provider circuit open")

    registry.register("web_search", broken_tool)
    with pytest.raises(InfrastructureError, match="circuit open"):
        await registry.get("web_search")("inis", 5)


def test_failed_tool_can_be_replaced_after_unregister() -> None:
    """Recovery path: the planner can swap the unavailable tool (§41.8)."""
    registry = ToolRegistry()

    async def degraded(*args, **kwargs):
        return "degraded-answer"

    registry.register("web_search", degraded)
    assert registry.get("web_search") is degraded
    registry.unregister("web_search")
    with pytest.raises(KeyError):
        registry.get("web_search")
