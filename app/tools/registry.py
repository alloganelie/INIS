"""Tool Registry for INIS internal tools per spec §21."""

from typing import Callable


class ToolRegistry:
    """Registry for internal tools with signatures per §21."""

    def __init__(self) -> None:
        """Initialize the tool registry."""
        self._tools: dict[str, Callable] = {}

    def register(self, name: str, fn: Callable) -> None:
        """Register a tool function.

        Args:
            name: Tool name.
            fn: Tool function (async callable).

        Raises:
            ValueError: If tool name is already registered.
        """
        if name in self._tools:
            raise ValueError(f"Tool '{name}' is already registered")
        self._tools[name] = fn

    def get(self, name: str) -> Callable:
        """Get a tool function by name.

        Args:
            name: Tool name.

        Returns:
            Tool function.

        Raises:
            KeyError: If tool is not registered.
        """
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found in registry")
        return self._tools[name]

    def list(self) -> list[str]:
        """List all registered tool names.

        Returns:
            List of tool names.
        """
        return list(self._tools.keys())

    def unregister(self, name: str) -> None:
        """Unregister a tool.

        Args:
            name: Tool name.

        Raises:
            KeyError: If tool is not registered.
        """
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not found in registry")
        del self._tools[name]
