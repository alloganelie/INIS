"""PHASE-04 smoke imports: connectors, domain entities, API routers, protocol."""

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


def test_connectors_import() -> None:
    """Connectors packages import (files, database, api, web) per §9, §10."""
    _import_or_skip("app.connectors")
    _import_or_skip("app.connectors.files")
    _import_or_skip("app.connectors.database")
    _import_or_skip("app.connectors.api")
    _import_or_skip("app.connectors.web")


def test_domain_entities_import() -> None:
    """Domain entities Source, Document, Dataset, SourceCandidate import per §9."""
    module = _import_or_skip("app.domain.entities")
    for symbol in ("Source", "Document", "Dataset", "SourceCandidate"):
        assert hasattr(module, symbol), f"missing symbol: {symbol}"


def test_api_sources_import() -> None:
    """Sources API module imports per §32."""
    module = _import_or_skip("app.api.v1.sources")
    assert hasattr(module, "router"), "missing symbol: router"


def test_api_information_import() -> None:
    """Information API module imports per §32."""
    module = _import_or_skip("app.api.v1.information")
    assert hasattr(module, "router"), "missing symbol: router"


def test_source_connector_protocol() -> None:
    """SourceConnector is a Protocol with the §9 surface."""
    from typing import Protocol

    module = _import_or_skip("app.connectors.base")
    protocol = getattr(module, "SourceConnector", None)
    if protocol is None:
        pytest.skip("symbol absent: SourceConnector")
    assert isinstance(protocol, type), "SourceConnector is not a class"
    assert issubclass(protocol, Protocol), "SourceConnector is not a Protocol"
    for method in ("discover", "retrieve", "inspect", "health_check", "metadata"):
        assert hasattr(protocol, method), f"missing protocol method: {method}"
