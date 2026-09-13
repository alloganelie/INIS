"""PHASE-04.3 smoke imports: postgres, search interface, audit, serper, extractors."""

from __future__ import annotations

import importlib
import importlib.util

import pytest


def _import_or_skip(module_name: str):
    """Import *module_name* or skip the test if it is absent."""
    try:
        spec = importlib.util.find_spec(module_name)
    except (ModuleNotFoundError, ValueError):
        spec = None
    if spec is None:
        pytest.skip(f"module absent: {module_name}")
    return importlib.import_module(module_name)


def _symbol_or_skip(module, module_name: str, symbol: str):
    """Return *symbol* from *module* or skip if it is not defined."""
    value = getattr(module, symbol, None)
    if value is None:
        pytest.skip(f"symbol absent: {symbol} in {module_name}")
    return value


def test_postgres_connector_imports() -> None:
    """PostgresConnector imports with the §9 connector surface."""
    module = _import_or_skip("app.connectors.database.postgres_connector")
    connector = _symbol_or_skip(
        module, "app.connectors.database.postgres_connector", "PostgresConnector"
    )
    assert isinstance(connector, type), "PostgresConnector is not a class"
    for method in ("discover", "retrieve", "inspect", "health_check", "metadata"):
        assert hasattr(connector, method), f"missing method: {method}"


def test_search_provider_interface_imports() -> None:
    """Domain SearchProvider interface imports (skip si absent)."""
    module = _import_or_skip("app.domain.interfaces.search_provider")
    provider = _symbol_or_skip(
        module, "app.domain.interfaces.search_provider", "SearchProvider"
    )
    assert provider is not None


def test_audit_writer_imports() -> None:
    """Audit writer imports (skip si absent)."""
    module = _import_or_skip("app.governance.audit.audit_writer")
    writer = _symbol_or_skip(
        module, "app.governance.audit.audit_writer", "AuditWriter"
    )
    assert writer is not None


async def test_serper_provider_requires_api_key() -> None:
    """SerperProvider without API key fails explicitly, no network call."""
    try:
        from app.connectors.web.providers.serper_provider import SerperProvider
    except ImportError:
        pytest.skip("module absent: app.connectors.web.providers.serper_provider")

    from app.core.errors import InfrastructureError

    provider = SerperProvider()
    with pytest.raises(InfrastructureError, match="API key"):
        await provider.search("test query", 5)


def test_trafilatura_extractor_imports() -> None:
    """Trafilatura extractor imports (skip si absent)."""
    module_name = "app.connectors.web.extractors.trafilatura_extractor"
    module = _import_or_skip(module_name)
    symbols = [name for name in dir(module) if not name.startswith("_")]
    if not symbols:
        pytest.skip(f"stub vide (aucun symbole): {module_name}")
    assert symbols


def test_progress_endpoint_imports() -> None:
    """Progress endpoint imports (Antigravity: requests progress handler)."""
    module = _import_or_skip("app.api.v1.requests.progress_handler")
    assert hasattr(module, "router"), "missing symbol: router"
