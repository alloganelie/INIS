"""§9.2 — registry of externally registered source connectors.

OCR, audio, video and real-time streaming are excluded from V1 (§9.2) but MUST
be *foreseen as plugins*. Any distribution can register a connector under the
``inis.connectors`` entry-point group and be discovered here, without touching
the core.

Entry-point contract: the target is a **factory** — a callable (usually a class)
that returns an object satisfying :class:`~app.connectors.base.SourceConnector`.
A connector whose engine is not installed must still *declare* its capability
(``metadata().supported_source_types``) but **refuse** its operations (raise,
never fabricate data). The registry never swallows that refusal.

Discovery is lazy: reading the installed metadata costs nothing until the first
call, and instantiating a connector is a separate step.
"""

from __future__ import annotations

import importlib.metadata
from typing import Any

from app.connectors.base import SourceConnector

__all__ = [
    "PLUGIN_GROUP",
    "discover_plugins",
    "load_all_plugins",
    "load_plugin",
    "plugin_names",
]

#: The entry-point group an external source connector registers under (§9.2).
PLUGIN_GROUP = "inis.connectors"


def discover_plugins() -> dict[str, importlib.metadata.EntryPoint]:
    """Return the ``inis.connectors`` entry points, keyed by name."""
    entry_points = importlib.metadata.entry_points()
    if hasattr(entry_points, "select"):
        selected = entry_points.select(group=PLUGIN_GROUP)
    else:  # pragma: no cover - compatibility path for older importlib.metadata
        selected = entry_points.get(PLUGIN_GROUP, [])
    return {entry_point.name: entry_point for entry_point in selected}


def load_plugin(name: str) -> SourceConnector | None:
    """Instantiate one registered connector by name; ``None`` when unknown.

    A broken entry point (missing target, wrong signature, import error) is
    reported **loudly**: a plugin that cannot load must not silently disappear
    from the capability list.
    """
    entry_point = discover_plugins().get(name)
    if entry_point is None:
        return None
    factory: Any = entry_point.load()
    return factory() if callable(factory) else factory


def load_all_plugins() -> dict[str, SourceConnector]:
    """Instantiate every registered connector (name → instance)."""
    loaded: dict[str, SourceConnector] = {}
    for name in discover_plugins():
        connector = load_plugin(name)
        if connector is not None:
            loaded[name] = connector
    return loaded


def plugin_names() -> list[str]:
    """Return the registered connector names, sorted for a stable output."""
    return sorted(discover_plugins())
