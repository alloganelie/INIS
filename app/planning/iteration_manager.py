"""Management of iteration lifecycle and decision-making (§8.3)."""

from datetime import UTC, datetime
from typing import Any

from app.domain.value_objects.ulid import ULID


class IterationManager:
    """Manage iteration structure and continuation decisions per §8.3."""

    def start_iteration(
        self,
        request_id: str,
        iteration_number: int,
        objective: str,
        hypothesis: str | None = None,
    ) -> dict[str, Any]:
        """Create a new iteration structure per §8.3.

        Args:
            request_id: The request this iteration belongs to.
            iteration_number: Sequential iteration number.
            objective: Objective of this iteration.
            hypothesis: Working hypothesis for this iteration.

        Returns:
            Iteration dictionary conforming to §8.3 structure.
        """
        return {
            "iteration_id": ULID.new("ITER_"),
            "request_id": request_id,
            "iteration_number": iteration_number,
            "objective": objective,
            "hypothesis": hypothesis or "",
            "actions": [],
            "tools_used": [],
            "inputs": [],
            "outputs": [],
            "new_evidence": [],
            "decision": "continue",
            "termination_reason": None,
        }

    def complete_iteration(
        self,
        iteration: dict[str, Any],
        decision: str,
        termination_reason: str | None = None,
    ) -> dict[str, Any]:
        """Mark an iteration as complete with a decision.

        Args:
            iteration: The iteration to complete.
            decision: Final decision (continue, stop, delegate, fail).
            termination_reason: Reason if stopping/terminating.

        Returns:
            Updated iteration dictionary.
        """
        iteration["decision"] = decision
        iteration["termination_reason"] = termination_reason
        return iteration

    def should_continue(
        self,
        iteration: dict[str, Any],
        requirements_satisfied: bool = False,
        confidence_score: float = 0.0,
        minimum_confidence: float = 0.8,
        budget_exhausted: bool = False,
        no_new_relevant_source: bool = False,
        information_unavailable: bool = False,
        policy_forbids_continue: bool = False,
    ) -> bool:
        """Determine if execution should continue based on §8.5 criteria.

        Args:
            iteration: Current iteration state.
            requirements_satisfied: Whether requirements are met.
            confidence_score: Current confidence score.
            minimum_confidence: Minimum required confidence.
            budget_exhausted: Whether budget is exhausted.
            no_new_relevant_source: Whether no new relevant sources found.
            information_unavailable: Whether information is unavailable.
            policy_forbids_continue: Whether policy forbids continuation.

        Returns:
            True if execution should continue, False otherwise.
        """
        # Stop if requirements are satisfied
        if requirements_satisfied:
            return False
        
        # Stop if confidence threshold is met
        if confidence_score >= minimum_confidence:
            return False
        
        # Stop if budget is exhausted
        if budget_exhausted:
            return False
        
        # Stop if no new relevant sources
        if no_new_relevant_source:
            return False
        
        # Stop if information is unavailable
        if information_unavailable:
            return False
        
        # Stop if policy forbids continuation
        if policy_forbids_continue:
            return False
        
        return True

    def record_action(
        self, iteration: dict[str, Any], action: str, tool: str, inputs: dict[str, Any]
    ) -> None:
        """Record an action taken during the iteration."""
        iteration["actions"].append(
            {"action": action, "tool": tool, "inputs": inputs, "timestamp": datetime.now(UTC).isoformat()}
        )

    def record_tool_usage(self, iteration: dict[str, Any], tool: str) -> None:
        """Record a tool used during the iteration."""
        if tool not in iteration["tools_used"]:
            iteration["tools_used"].append(tool)

    def record_output(self, iteration: dict[str, Any], output: Any) -> None:
        """Record an output from the iteration."""
        iteration["outputs"].append(output)

    def record_evidence(self, iteration: dict[str, Any], evidence_id: str) -> None:
        """Record new evidence discovered during the iteration."""
        iteration["new_evidence"].append(evidence_id)
