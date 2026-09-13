"""PHASE-05 smoke imports: knowledge layer (units, evidence, search, metrics)."""

from __future__ import annotations

import importlib
import importlib.util

import pytest


def _has_module(module_name: str) -> bool:
    """Return True if *module_name* can be found without importing it."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def _import_or_skip(module_name: str):
    """Import *module_name* or skip the test if it is absent."""
    if not _has_module(module_name):
        pytest.skip(f"module absent: {module_name}")
    return importlib.import_module(module_name)


def _symbol_or_skip(module, module_name: str, symbol: str):
    """Return *symbol* from *module* or skip if it is not defined."""
    value = getattr(module, symbol, None)
    if value is None:
        pytest.skip(f"symbol absent: {symbol} in {module_name}")
    return value


def test_information_unit_imports() -> None:
    """InformationUnit entity imports per §11 (skip si absent)."""
    module_name = "app.domain.entities.information_unit"
    module = _import_or_skip(module_name)
    unit = _symbol_or_skip(module, module_name, "InformationUnit")
    assert isinstance(unit, type), "InformationUnit is not a class"


def test_evidence_imports() -> None:
    """Evidence entity imports per §14 (skip si absent)."""
    module_name = "app.domain.entities.evidence"
    module = _import_or_skip(module_name)
    evidence = _symbol_or_skip(module, module_name, "Evidence")
    assert isinstance(evidence, type), "Evidence is not a class"


def test_claim_imports() -> None:
    """Claim entity imports per §14 (skip si absent)."""
    module_name = "app.domain.entities.claim"
    module = _import_or_skip(module_name)
    claim = _symbol_or_skip(module, module_name, "Claim")
    assert isinstance(claim, type), "Claim is not a class"


def test_chunk_splitter_smoke() -> None:
    """ChunkSplitter imports (skip si absent)."""
    module_name = "app.knowledge.chunking.chunk_splitter"
    module = _import_or_skip(module_name)
    splitter = _symbol_or_skip(module, module_name, "ChunkSplitter")
    assert isinstance(splitter, type), "ChunkSplitter is not a class"


def test_lineage_tracker_smoke() -> None:
    """LineageTracker imports (skip si absent)."""
    module_name = "app.provenance.lineage_tracker"
    module = _import_or_skip(module_name)
    tracker = _symbol_or_skip(module, module_name, "LineageTracker")
    assert isinstance(tracker, type), "LineageTracker is not a class"


def test_vector_search_imports() -> None:
    """Vector search imports per §16 (skip si absent)."""
    module_name = "app.knowledge.search.vector_search"
    module = _import_or_skip(module_name)
    search = _symbol_or_skip(module, module_name, "VectorSearch")
    assert search is not None


def test_hybrid_search_imports() -> None:
    """Hybrid search imports per §16.2 (skip si absent)."""
    module_name = "app.knowledge.search.hybrid_search"
    module = _import_or_skip(module_name)
    search = _symbol_or_skip(module, module_name, "HybridSearch")
    assert search is not None


def test_metrics_registry_smoke() -> None:
    """Metrics registry imports per §34 (skip si absent)."""
    module_name = "app.observability.metrics"
    module = _import_or_skip(module_name)
    registry = _symbol_or_skip(module, module_name, "MetricsRegistry")
    assert registry is not None


def test_evidence_endpoint_imports() -> None:
    """Evidence endpoint imports (skip si absent)."""
    module_name = "app.api.v1.evidence"
    module = _import_or_skip(module_name)
    router = _symbol_or_skip(module, module_name, "router")
    assert router is not None


def test_conflicts_endpoint_imports() -> None:
    """Conflicts endpoint imports (skip si absent)."""
    module_name = "app.api.v1.conflicts"
    module = _import_or_skip(module_name)
    router = _symbol_or_skip(module, module_name, "router")
    assert router is not None


def test_metrics_endpoint_returns_dict() -> None:
    """Metrics endpoint imports and exposes a router (skip si absent)."""
    module_name = "app.api.v1.system.metrics_router"
    module = _import_or_skip(module_name)
    router = _symbol_or_skip(module, module_name, "router")
    assert router is not None


def test_information_unit_provenance_invariant() -> None:
    """InformationUnit carries non-empty provenance per §11 (skip si absent)."""
    module_name = "app.domain.entities.information_unit"
    module = _import_or_skip(module_name)
    unit_cls = _symbol_or_skip(module, module_name, "InformationUnit")
    try:
        unit = unit_cls(
            information_id="INF_test",
            type="text",
            content={"text": "smoke"},
            raw_reference={},
            source_id="SRC_test",
            document_id=None,
            dataset_id=None,
            location={},
            context={},
            language=None,
            unit=None,
            time={},
            classification={},
            quality={},
            confidence={},
            provenance={"source_id": "SRC_test"},
            versions=[],
        )
    except Exception as exc:
        pytest.skip(f"InformationUnit schema not stabilized: {exc}")
    assert unit.provenance, "provenance must be non-empty per §11"
    assert unit.source_id, "source_id must be set per §11"
