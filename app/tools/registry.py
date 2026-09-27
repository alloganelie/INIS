"""Tool Registry for INIS internal tools per spec §21."""

from typing import Any, Callable


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

    async def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Execute a registered tool, feeding the §34 ``tool_failure_rate``.

        The failure is re-raised: observability records it, it never swallows
        it (§0.2 — an unavailable tool must stay visible to the planner).

        Raises:
            KeyError: If the tool is not registered.
        """
        tool = self.get(name)
        try:
            return await tool(*args, **kwargs)
        except Exception:
            try:
                from app.observability.metrics import record_outcome

                record_outcome("tool_failure_rate", failure=True)
            except Exception:  # noqa: BLE001 - observability never hides failures
                pass
            raise

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
