"""§9.2 — a plugin declared but not installed must degrade loudly, never invent.

The ``ocr`` connector (excluded from V1, foreseen as a plugin) registers its
capability — ``metadata().supported_source_types == ["ocr"]`` — but its engine is
not installed, so every *operation* refuses with a named error. The registry
loads it (the capability is visible) and the refusal is **not** swallowed: a
caller learns the plugin is absent, it never receives fabricated content.
"""

from __future__ import annotations

from typing import ClassVar

import pytest

from app.connectors import plugins
from app.connectors.base import ConnectorMetadata, HealthStatus, Query, SourceCandidate


class OcrConnectorWithoutEngine:
    """A source type ``ocr`` whose engine is absent from the deployment."""

    connector_id: ClassVar[str] = "ocr"
    supported_source_types: ClassVar[list[str]] = ["ocr"]

    async def discover(self, query):
        raise NotImplementedError("moteur OCR non installé (§9.2 : plugin à venir)")

    async def retrieve(self, candidate):
        raise NotImplementedError("moteur OCR non installé (§9.2 : plugin à venir)")

    async def inspect(self, raw):
        raise NotImplementedError("moteur OCR non installé (§9.2 : plugin à venir)")

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
    def __init__(self, name: str, factory: object) -> None:
        self.name = name
        self._factory = factory

    def load(self) -> object:
        return self._factory


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        plugins,
        "discover_plugins",
        lambda: {"ocr": _FakeEntryPoint("ocr", OcrConnectorWithoutEngine)},
    )


@pytest.mark.asyncio
async def test_the_capability_is_declared_even_though_the_engine_is_absent(
    registry: None,
) -> None:
    connector = plugins.load_plugin("ocr")

    assert connector is not None
    metadata = await connector.metadata()
    assert metadata.supported_source_types == ["ocr"], "la capacité est visible"


@pytest.mark.asyncio
async def test_operations_refuse_instead_of_fabricating(registry: None) -> None:
    connector = plugins.load_plugin("ocr")

    assert connector is not None
    with pytest.raises(NotImplementedError, match="non installé"):
        await connector.discover(Query())
    with pytest.raises(NotImplementedError, match="non installé"):
        await connector.retrieve(SourceCandidate(source_id="SRC_x", location="file://scan.png", metadata={}))


@pytest.mark.asyncio
async def test_health_is_reported_unhealthy_not_hidden(registry: None) -> None:
    connector = plugins.load_plugin("ocr")

    assert connector is not None
    health = await connector.health_check()
    assert health.healthy is False
    assert "non installé" in health.message


def test_the_normal_registry_is_unaffected_by_a_refusing_plugin(registry: None) -> None:
    loaded = plugins.load_all_plugins()

    assert "ocr" in loaded, "le plugin absent reste listé"
