"""Evaluate the stopping criteria specified by INIS section 8.5."""

from dataclasses import dataclass
from enum import StrEnum


class TerminationReason(StrEnum):
    """Canonical reasons an iteration may stop."""

    REQUIREMENTS_SATISFIED = "requirements_satisfied"
    CONFIDENCE_REACHED = "confidence_reached"
    BUDGET_EXHAUSTED = "budget_exhausted"
    NO_NEW_RELEVANT_SOURCE = "no_new_relevant_source"
    INFORMATION_UNAVAILABLE = "information_unavailable"
    POLICY_FORBIDS_CONTINUE = "policy_forbids_continue"
    CONTINUE = "continue"


@dataclass(frozen=True)
class TerminationContext:
    """Observed execution state used to make a deterministic termination decision."""

    requirements_satisfied: bool = False
    confidence_score: float = 0.0
    minimum_confidence: float = 0.8
    budget_exhausted: bool = False
    no_new_relevant_source: bool = False
    information_unavailable: bool = False
    policy_forbids_continue: bool = False


@dataclass(frozen=True)
class TerminationDecision:
    """A stop/continue decision with its most actionable reason."""

    should_terminate: bool
    reason: TerminationReason


class TerminationEvaluator:
    """Apply §8.5 in safety-first order."""

    def evaluate(self, context: TerminationContext) -> TerminationDecision:
        """Stop whenever a specified condition is true."""
        conditions = (
            (context.policy_forbids_continue, TerminationReason.POLICY_FORBIDS_CONTINUE),
            (context.budget_exhausted, TerminationReason.BUDGET_EXHAUSTED),
            (context.information_unavailable, TerminationReason.INFORMATION_UNAVAILABLE),
            (context.no_new_relevant_source, TerminationReason.NO_NEW_RELEVANT_SOURCE),
            (context.requirements_satisfied, TerminationReason.REQUIREMENTS_SATISFIED),
            (
                context.confidence_score >= context.minimum_confidence,
                TerminationReason.CONFIDENCE_REACHED,
            ),
        )
        for condition, reason in conditions:
            if condition:
                return TerminationDecision(should_terminate=True, reason=reason)
        return TerminationDecision(should_terminate=False, reason=TerminationReason.CONTINUE)
