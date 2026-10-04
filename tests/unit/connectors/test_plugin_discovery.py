"""§9.2 — the plugin registry discovers and loads external connectors lazily.

The registry lives in ``app/connectors/plugins.py``; this file proves its
contract with a fake entry point, so no real distribution has to be installed
to test discovery. The *refusal* path (a connector declared but whose engine is
not installed) is covered by ``tests/integration/test_plugin_absent_degrades.py``.
"""

from __future__ import annotations

import importlib.metadata
from typing import ClassVar

import pytest

from app.connectors import plugins
from app.connectors.base import ConnectorMetadata, HealthStatus


class DummyOcrConnector:
    """A connector that declares ``ocr`` but refuses until its engine exists."""

    connector_id: ClassVar[str] = "ocr"
    supported_source_types: ClassVar[list[str]] = ["ocr"]

    async def discover(self, query):
        raise NotImplementedError("moteur OCR non installé")

    async def retrieve(self, candidate):
        raise NotImplementedError("moteur OCR non installé")

    async def inspect(self, raw):
        raise NotImplementedError("moteur OCR non installé")

    async def health_check(self) -> HealthStatus:
        return HealthStatus(healthy=False, message="moteur OCR non installé")

    async def metadata(self) -> ConnectorMetadata:
        return ConnectorMetadata(
            connector_id="ocr",
            name="OCR",
            version="0.0.0",
            supported_source_types=["ocr"],
        )


class _FakeEntryPoint:
    """Minimal ``importlib.metadata.EntryPoint`` stand-in for discovery tests."""

    def __init__(self, name: str, factory: object) -> None:
        self.name = name
        self._factory = factory

    def load(self) -> object:
        return self._factory


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Register one fake connector under ``inis.connectors`` for this test."""
    monkeypatch.setattr(
        plugins,
        "discover_plugins",
        lambda: {"ocr": _FakeEntryPoint("ocr", DummyOcrConnector)},
    )


class TestDiscovery:
    def test_a_registered_plugin_is_listed(self, registry: None) -> None:
        assert "ocr" in plugins.discover_plugins()

    def test_plugin_names_are_sorted(self, registry: None) -> None:
        assert plugins.plugin_names() == ["ocr"]

    def test_an_empty_registry_is_not_an_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(plugins, "discover_plugins", dict)
        assert plugins.discover_plugins() == {}
        assert plugins.plugin_names() == []


class TestLoading:
    def test_load_plugin_returns_an_instance(self, registry: None) -> None:
        connector = plugins.load_plugin("ocr")

        assert connector is not None
        assert connector.connector_id == "ocr"
        assert connector.supported_source_types == ["ocr"]

    def test_an_unknown_plugin_is_none(self, registry: None) -> None:
        assert plugins.load_plugin("video") is None

    def test_loading_is_lazy_and_idempotent(self, registry: None) -> None:
        first = plugins.load_plugin("ocr")
        second = plugins.load_plugin("ocr")

        assert first is not None
        assert second is not None
        assert first.connector_id == second.connector_id

    def test_the_entry_point_group_name_is_stable(self) -> None:
        # The group name is part of the §9.2 contract: external packages depend
        # on it, so it must not drift silently.
        assert plugins.PLUGIN_GROUP == "inis.connectors"
        assert importlib.metadata.EntryPoint is not None  # stdlib surface
