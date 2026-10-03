"""§17.1/§8.4 — the early-stop decision, and what must never trigger it.

``memory_lookup`` answers "does the run already know?"; this decision answers
"may the run therefore stop acquiring?". The two are deliberately separate: a
sufficient memory that was consulted in a *degraded* mode is reused but does not
stop anything, which is the guard the plan asks for — a few units sharing words
with the question must never cut a run short.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.domain.entities.memory_result import MemoryCandidate, MemoryResult
from app.planning.memory_checker import (
    SUFFICIENCY_CRITERIA,
    EarlyStopDecision,
    early_stop_decision,
)

CANDIDATE = MemoryCandidate(
    information_id="INF_01M3Q0000000000000000000ES",
    content={"subject": "Paris", "predicate": "population", "value": 2148000},
    source_id="SRC_01M3Q0000000000000000000ES",
    provenance={"source_id": "SRC_01M3Q0000000000000000000ES"},
)


def _sufficient() -> MemoryResult:
    """Return the §17.1 lookup outcome that reused one candidate."""
    return MemoryResult(sufficient=True, items=(CANDIDATE,), question="population de Paris")


def _insufficient(reason: str = "no candidate found") -> MemoryResult:
    """Return the §17.1 lookup outcome that found nothing reusable."""
    return MemoryResult(sufficient=False, items=(), reason=reason, question="population")


class TestTheStopIsDecided:
    """``stopped_acquisition`` is what the run obeys, not ``sufficient``."""

    def test_a_hybrid_lookup_without_limitation_may_stop(self) -> None:
        decision = early_stop_decision(_sufficient(), mode="hybrid")

        assert decision.sufficient is True
        assert decision.stopped_acquisition is True
        assert decision.criteria == SUFFICIENCY_CRITERIA
        assert decision.withheld_reason is None
        assert decision.information_ids == (CANDIDATE.information_id,)
        assert decision.mode == "hybrid"

    def test_the_decision_names_its_criteria(self) -> None:
        """A reader must see *why* the run concluded, not only that it did."""
        decision = early_stop_decision(_sufficient(), mode="hybrid")
        assert set(decision.criteria) == {
            "provenance_complete",
            "freshness_acceptable",
            "policy_allows_reuse",
        }

    def test_the_projection_is_shared_by_colis_audit_and_ui(self) -> None:
        payload = early_stop_decision(_sufficient(), mode="hybrid").to_dict()
        assert payload == {
            "sufficient": True,
            "stopped_acquisition": True,
            "criteria": list(SUFFICIENCY_CRITERIA),
            "withheld_reason": None,
            "mode": "hybrid",
            "information_ids": [CANDIDATE.information_id],
        }


class TestWhatNeverStopsARun:
    """The negative cases the plan requires, one by one."""

    def test_an_insufficient_memory_does_not_stop(self) -> None:
        decision = early_stop_decision(_insufficient(), mode="hybrid")

        assert decision.sufficient is False
        assert decision.stopped_acquisition is False
        assert decision.criteria == ()
        assert decision.information_ids == ()
        assert decision.withheld_reason == "no candidate found"

    def test_a_lexical_only_memory_never_stops_the_acquisition(self) -> None:
        """A lexical hit is a guess about relevance: reuse yes, stop no."""
        decision = early_stop_decision(_sufficient(), mode="lexical_only")

        assert decision.sufficient is True
        assert decision.stopped_acquisition is False
        assert decision.withheld_reason is not None
        assert "lexical_only" in decision.withheld_reason
        assert decision.information_ids == (CANDIDATE.information_id,), (
            "l'unité reste réutilisée : rien n'est perdu, seul l'arrêt est refusé"
        )

    def test_an_unavailable_memory_does_not_stop(self) -> None:
        decision = early_stop_decision(_sufficient(), mode="unavailable")
        assert decision.stopped_acquisition is False

    def test_a_limited_lookup_does_not_stop(self) -> None:
        """A search that declared what it could not do cannot conclude."""
        decision = early_stop_decision(
            _sufficient(),
            mode="hybrid",
            limitations=["2 candidat(s) sans vecteur n'ont pas été évalués"],
        )

        assert decision.sufficient is True
        assert decision.stopped_acquisition is False
        assert "sans vecteur" in str(decision.withheld_reason)

    def test_the_withheld_reason_quotes_the_limitation(self) -> None:
        decision = early_stop_decision(
            _sufficient(), mode="hybrid", limitations=["comparaison partielle"]
        )
        assert "comparaison partielle" in str(decision.withheld_reason)

    @pytest.mark.parametrize("mode", ["lexical_only", "unavailable", "unknown"])
    def test_only_the_hybrid_mode_can_conclude(self, mode: str) -> None:
        assert early_stop_decision(_sufficient(), mode=mode).stopped_acquisition is False

    def test_a_candidate_that_fails_a_filter_is_not_sufficient(self) -> None:
        """The §17.1 filters stay the source of sufficiency: no shortcut here."""
        rejected = MemoryResult(
            sufficient=False,
            items=(),
            reason="INF_X: stale; INF_Y: reuse forbidden by policy",
        )
        decision = early_stop_decision(rejected, mode="hybrid")
        assert decision.stopped_acquisition is False
        assert "stale" in str(decision.withheld_reason)


class TestTheDecisionIsAFrozenValue:
    """The decision travels in the colis and the audit: it must not drift."""

    def test_the_decision_is_immutable(self) -> None:
        decision = early_stop_decision(_sufficient(), mode="hybrid")
        assert isinstance(decision, EarlyStopDecision)
        with pytest.raises(FrozenInstanceError):
            decision.stopped_acquisition = False  # type: ignore[misc]
