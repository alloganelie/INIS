"""Tests for the confidence explainer and dimension functions (§15.1)."""

from datetime import datetime
from datetime import timezone

from app.confidence.confidence_explainer import DIMENSION_ORDER
from app.confidence.confidence_explainer import explain
from app.confidence.dimensions import cross_source_agreement
from app.confidence.dimensions import data_quality_signal
from app.confidence.dimensions import evidence_strength
from app.confidence.dimensions import extraction_confidence
from app.confidence.dimensions import methodological_consistency
from app.confidence.dimensions import source_freshness
from app.confidence.dimensions import source_reliability
from app.domain.entities.evidence import Evidence


class TestConfidenceExplainer:
    """2 tests covering explanation content and determinism."""

    def test_explain_covers_all_dimensions(self) -> None:
        """Explanation names the 7 dimensions, weights and total."""
        text = explain({name: 0.5 for name in DIMENSION_ORDER})

        for name in DIMENSION_ORDER:
            assert name in text
        assert "total = 0.5000" in text
        assert "not a probability" in text

    def test_explain_is_deterministic(self) -> None:
        """Same input yields byte-identical explanation."""
        dimensions = {name: 0.8 for name in DIMENSION_ORDER}

        assert explain(dimensions) == explain(dimensions)


class TestDimensions:
    """4 tests covering signals, clamping, neutrals and real entities."""

    def test_reliability_reads_score_and_clamps(self) -> None:
        """reliability_score is used clamped; missing score is neutral."""
        assert source_reliability.compute({"reliability_score": 0.9}) == 0.9
        assert source_reliability.compute({"reliability_score": 1.5}) == 1.0
        assert source_reliability.compute({}) == 0.5

    def test_freshness_decays_over_a_year(self) -> None:
        """Fresh sources score high, year-old sources score 0.0."""
        from pytest import approx

        now = datetime(2024, 6, 1, tzinfo=timezone.utc)

        fresh = source_freshness.compute({"published_at": "2024-05-01T00:00:00Z"}, now=now)
        stale = source_freshness.compute({"published_at": "2023-01-01T00:00:00Z"}, now=now)

        assert fresh == approx(1.0 - 31.0 / 365.0)  # 31 days old
        assert stale == 0.0
        assert source_freshness.compute({}, now=now) == 0.5

    def test_evidence_strength_reads_real_entity(self) -> None:
        """Codex Evidence.strength drives the dimension (dicts too)."""
        evidence = Evidence(
            evidence_id="EVID_01",
            claim_id=None,
            information_id="INF_01",
            document_id="DOC_01",
            source_id="SRC_01",
            excerpt="excerpt",
            location={},
            strength=0.7,
        )

        assert evidence_strength.compute(evidence) == 0.7
        assert evidence_strength.compute({"strength": 0.4}) == 0.4
        assert evidence_strength.compute({}) == 0.5

    def test_aggregates_average_or_neutral(self) -> None:
        """Agreement/consistency average signals; empty lists score 0.0."""
        assert cross_source_agreement.compute([{"agreement": 1.0}, {"agreement": 0.0}]) == 0.5
        assert cross_source_agreement.compute([{"title": "x"}]) == 0.5
        assert cross_source_agreement.compute([]) == 0.0
        assert methodological_consistency.compute([{"consistency": 0.8}]) == 0.8
        assert methodological_consistency.compute([]) == 0.0
        assert extraction_confidence.compute({"extraction_confidence": 2.0}) == 1.0
        assert data_quality_signal.compute({"quality_score": 0.3}) == 0.3
