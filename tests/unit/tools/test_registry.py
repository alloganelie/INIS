"""Tests for ToolRegistry per INIS spec §21."""

import pytest

from app.tools.registry import ToolRegistry


async def dummy_tool(x: int) -> int:
    """Dummy async tool for testing."""
    return x * 2


def test_register_and_get() -> None:
    """Test registering and retrieving a tool."""
    registry = ToolRegistry()
    registry.register("double", dummy_tool)
    retrieved = registry.get("double")
    assert retrieved == dummy_tool


def test_list() -> None:
    """Test listing all registered tools."""
    registry = ToolRegistry()
    registry.register("double", dummy_tool)
    registry.register("triple", dummy_tool)
    tools = registry.list()
    assert set(tools) == {"double", "triple"}


def test_unregister() -> None:
    """Test unregistering a tool."""
    registry = ToolRegistry()
    registry.register("double", dummy_tool)
    registry.unregister("double")
    with pytest.raises(KeyError, match="Tool 'double' not found"):
        registry.get("double")
