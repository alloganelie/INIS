"""Unit tests for the §8.5 termination criteria.

``TerminationEvaluator`` stops an iteration as soon as one of the six §8.5
conditions holds, in safety-first order (a policy veto outranks a satisfied
requirement, and an exhausted budget outranks both).
"""

from __future__ import annotations

import pytest

from app.agents.decision.termination_evaluator import (
    TerminationContext,
    TerminationDecision,
    TerminationEvaluator,
    TerminationReason,
)


@pytest.fixture
def evaluator() -> TerminationEvaluator:
    """Return a stateless evaluator (the §8.5 decision is pure)."""
    return TerminationEvaluator()


class TestContinueDecision:
    """§8.5 — no condition holds, the cycle continues."""

    def test_default_context_continues(self, evaluator: TerminationEvaluator) -> None:
        """A fresh context has nothing satisfied → ``continue``."""
        decision = evaluator.evaluate(TerminationContext())
        assert decision.should_terminate is False
        assert decision.reason is TerminationReason.CONTINUE

    def test_confidence_below_threshold_continues(
        self, evaluator: TerminationEvaluator
    ) -> None:
        """0.79 < 0.8 minimum confidence does not stop the cycle."""
        decision = evaluator.evaluate(
            TerminationContext(confidence_score=0.79, minimum_confidence=0.8)
        )
        assert decision.should_terminate is False


class TestSingleConditions:
    """§8.5 — each documented condition stops the cycle on its own."""

    @pytest.mark.parametrize(
        ("context", "expected"),
        [
            (TerminationContext(requirements_satisfied=True), TerminationReason.REQUIREMENTS_SATISFIED),
            (
                TerminationContext(confidence_score=0.9, minimum_confidence=0.8),
                TerminationReason.CONFIDENCE_REACHED,
            ),
            (TerminationContext(budget_exhausted=True), TerminationReason.BUDGET_EXHAUSTED),
            (
                TerminationContext(no_new_relevant_source=True),
                TerminationReason.NO_NEW_RELEVANT_SOURCE,
            ),
            (
                TerminationContext(information_unavailable=True),
                TerminationReason.INFORMATION_UNAVAILABLE,
            ),
            (
                TerminationContext(policy_forbids_continue=True),
                TerminationReason.POLICY_FORBIDS_CONTINUE,
            ),
        ],
    )
    def test_condition_reports_its_reason(
        self,
        evaluator: TerminationEvaluator,
        context: TerminationContext,
        expected: TerminationReason,
    ) -> None:
        """The decision carries the actionable §8.5 reason."""
        decision = evaluator.evaluate(context)
        assert decision.should_terminate is True
        assert decision.reason is expected

    def test_confidence_at_threshold_stops(self, evaluator: TerminationEvaluator) -> None:
        """``>=`` minimum confidence is a stop condition, not a strict ``>``."""
        decision = evaluator.evaluate(
            TerminationContext(confidence_score=0.8, minimum_confidence=0.8)
        )
        assert decision.reason is TerminationReason.CONFIDENCE_REACHED


class TestSafetyFirstOrder:
    """§8.5 — precedence when several conditions hold simultaneously."""

    def test_policy_veto_outranks_everything(self, evaluator: TerminationEvaluator) -> None:
        """A forbidden continuation is reported even if the request succeeded."""
        decision = evaluator.evaluate(
            TerminationContext(
                policy_forbids_continue=True,
                budget_exhausted=True,
                requirements_satisfied=True,
                confidence_score=1.0,
            )
        )
        assert decision.reason is TerminationReason.POLICY_FORBIDS_CONTINUE

    def test_budget_outranks_requirements(self, evaluator: TerminationEvaluator) -> None:
        """An exhausted budget is reported before an unmet/unmet requirement."""
        decision = evaluator.evaluate(
            TerminationContext(budget_exhausted=True, requirements_satisfied=True)
        )
        assert decision.reason is TerminationReason.BUDGET_EXHAUSTED

    def test_information_unavailable_outranks_satisfied_requirements(
        self, evaluator: TerminationEvaluator
    ) -> None:
        """An unavailable source is a stronger signal than a satisfied form."""
        decision = evaluator.evaluate(
            TerminationContext(
                information_unavailable=True, requirements_satisfied=True
            )
        )
        assert decision.reason is TerminationReason.INFORMATION_UNAVAILABLE


class TestDecisionContract:
    """§8.5 — the decision is a frozen, serializable value."""

    def test_decision_is_frozen(self, evaluator: TerminationEvaluator) -> None:
        """Callers cannot mutate a decision after it is returned."""
        decision = evaluator.evaluate(TerminationContext())
        with pytest.raises(Exception):
            decision.should_terminate = True  # type: ignore[misc]

    def test_decision_equality(self) -> None:
        """Two identical decisions compare equal (comparable audit trail)."""
        assert TerminationDecision(False, TerminationReason.CONTINUE) == (
            TerminationDecision(False, TerminationReason.CONTINUE)
        )

    def test_reason_values_are_wire_ready(self) -> None:
        """Reasons are lowercase snake_case strings (§1.3 statuses)."""
        assert TerminationReason.REQUIREMENTS_SATISFIED == "requirements_satisfied"
        assert TerminationReason.BUDGET_EXHAUSTED == "budget_exhausted"

