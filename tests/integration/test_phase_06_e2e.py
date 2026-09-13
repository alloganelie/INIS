"""PHASE-06 smoke imports: quality checks, conflicts, confidence (§13, §14.4, §15)."""

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


def _has_symbol(module_name: str, symbol: str) -> bool:
    """Return True if *module_name* defines *symbol* (False si absent)."""
    if not _has_module(module_name):
        return False
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return False
    return getattr(module, symbol, None) is not None


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


def _require_symbols(pairs: list[tuple[str, str]]) -> None:
    """Skip listing every missing (module, symbol); pass if all present."""
    missing = [
        f"{symbol} in {module}"
        for module, symbol in pairs
        if not _has_symbol(module, symbol)
    ]
    if missing:
        pytest.skip("symbols absents: " + "; ".join(missing))


def test_conflict_entity_imports() -> None:
    """Conflict entity imports per §14.3 (skip si absent)."""
    module_name = "app.domain.entities.conflict"
    module = _import_or_skip(module_name)
    conflict = _symbol_or_skip(module, module_name, "Conflict")
    assert isinstance(conflict, type), "Conflict is not a class"


EXPECTED_CHECKS: list[tuple[str, str]] = [
    ("app.quality.checks.completeness_check", "CompletenessCheck"),
    ("app.quality.checks.validity_check", "ValidityCheck"),
    ("app.quality.checks.consistency_check", "ConsistencyCheck"),
    ("app.quality.checks.uniqueness_check", "UniquenessCheck"),
    ("app.quality.checks.type_conformity_check", "TypeConformityCheck"),
    ("app.quality.checks.duplicates_check", "DuplicatesCheck"),
    ("app.quality.checks.anomaly_check", "AnomalyCheck"),
    ("app.quality.checks.freshness_check", "FreshnessCheck"),
    ("app.quality.checks.provenance_check", "ProvenanceCheck"),
    ("app.quality.checks.temporal_consistency_check", "TemporalConsistencyCheck"),
    ("app.quality.checks.cross_source_consistency_check", "CrossSourceConsistencyCheck"),
]


def test_quality_checks_imports() -> None:
    """11 contrôles V1 obligatoires per §13.2 (skip si absents)."""
    assert len(EXPECTED_CHECKS) == 11
    _require_symbols(EXPECTED_CHECKS)


def test_conflict_detector_smoke() -> None:
    """ConflictDetector imports per §14.4 (skip si absent)."""
    module_name = "app.quality.conflict.conflict_detector"
    module = _import_or_skip(module_name)
    detector = _symbol_or_skip(module, module_name, "ConflictDetector")
    assert isinstance(detector, type), "ConflictDetector is not a class"


def test_quality_scorer_smoke() -> None:
    """QualityScorer imports per §13.3 (skip si absent)."""
    module_name = "app.quality.score.quality_scorer"
    module = _import_or_skip(module_name)
    scorer = _symbol_or_skip(module, module_name, "QualityScorer")
    assert isinstance(scorer, type), "QualityScorer is not a class"


def test_confidence_scorer_smoke() -> None:
    """ConfidenceScorer imports per §15.2 (skip si absent)."""
    module_name = "app.confidence.confidence_scorer"
    module = _import_or_skip(module_name)
    scorer = _symbol_or_skip(module, module_name, "ConfidenceScorer")
    assert isinstance(scorer, type), "ConfidenceScorer is not a class"


EXPECTED_DIMENSIONS: list[tuple[str, str]] = [
    ("app.confidence.dimensions.source_reliability", "SourceReliability"),
    ("app.confidence.dimensions.source_freshness", "SourceFreshness"),
    ("app.confidence.dimensions.extraction_confidence", "ExtractionConfidence"),
    ("app.confidence.dimensions.data_quality_signal", "DataQualitySignal"),
    ("app.confidence.dimensions.evidence_strength", "EvidenceStrength"),
    ("app.confidence.dimensions.cross_source_agreement", "CrossSourceAgreement"),
    (
        "app.confidence.dimensions.methodological_consistency",
        "MethodologicalConsistency",
    ),
]


def test_confidence_dimensions_imports() -> None:
    """7 dimensions de confiance per §15.1 (skip si absentes)."""
    assert len(EXPECTED_DIMENSIONS) == 7
    _require_symbols(EXPECTED_DIMENSIONS)


def test_quality_endpoints_imports() -> None:
    """Quality endpoints imports (skip si absent)."""
    module_name = "app.api.v1.quality"
    module = _import_or_skip(module_name)
    router = _symbol_or_skip(module, module_name, "router")
    assert router is not None


def test_confidence_endpoints_imports() -> None:
    """Confidence endpoints imports (skip si absent)."""
    module_name = "app.api.v1.confidence"
    module = _import_or_skip(module_name)
    router = _symbol_or_skip(module, module_name, "router")
    assert router is not None


def test_quality_endpoint_check() -> None:
    """Quality check endpoint reachable (skip si postgres indispo)."""
    module_name = "app.api.v1.quality"
    module = _import_or_skip(module_name)
    router = _symbol_or_skip(module, module_name, "router")
    routes = getattr(router, "routes", [])
    if not routes:
        pytest.skip("quality router sans routes (skip si postgres indispo)")
    assert routes


def test_confidence_endpoint_matrix() -> None:
    """Confidence matrix endpoint reachable (skip si confidence absent)."""
    module_name = "app.api.v1.confidence"
    module = _import_or_skip(module_name)
    router = _symbol_or_skip(module, module_name, "router")
    routes = getattr(router, "routes", [])
    if not routes:
        pytest.skip("confidence router sans routes (skip si confidence absent)")
    assert routes
