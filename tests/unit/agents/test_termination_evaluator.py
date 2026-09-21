"""Tests for section 8.5 termination decisions."""

from app.agents.decision.termination_evaluator import (
    TerminationContext,
    TerminationEvaluator,
    TerminationReason,
)


def test_stops_when_requirements_are_satisfied() -> None:
    decision = TerminationEvaluator().evaluate(TerminationContext(requirements_satisfied=True))

    assert decision.should_terminate is True
    assert decision.reason is TerminationReason.REQUIREMENTS_SATISFIED


def test_stops_when_confidence_reaches_requested_minimum() -> None:
    decision = TerminationEvaluator().evaluate(
        TerminationContext(confidence_score=0.8, minimum_confidence=0.8)
    )

    assert decision.should_terminate is True
    assert decision.reason is TerminationReason.CONFIDENCE_REACHED


def test_stops_for_budget_before_a_success_condition() -> None:
    decision = TerminationEvaluator().evaluate(
        TerminationContext(requirements_satisfied=True, budget_exhausted=True)
    )

    assert decision.should_terminate is True
    assert decision.reason is TerminationReason.BUDGET_EXHAUSTED
