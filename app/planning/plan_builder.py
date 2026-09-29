"""Construction of INIS plans from selected execution steps (§8.2, §8.4).

§8.4 defines a **closed** vocabulary of plan actions: ``ACTIONS`` in
:mod:`app.agents.pipeline.tool_dispatch` states, for each one, the §21 tools it
needs and whether the pipeline can execute it. A plan is the first place where
honesty is cheap, and it was the last place where it was applied:

* ``_build_step`` copied ``step["action"]`` verbatim, so a plan naming an action
  no tool implements was accepted and only refused much later, by the execution
  stage, step by step;
* the LLM path went further and promoted the free-text ``description`` of a step
  to the rank of *action* (``step.get("description") or step.get("action")``):
  a sentence written as prose decided what the pipeline would try to do.

This module refuses both cases before anything runs. An action outside the
vocabulary raises :class:`InvalidPlanAction` naming the action, its position and
the allowed ones; **no default action is ever substituted** (§0.2, §22.3, §37).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from app.core.errors import ValidationError
from app.domain.value_objects.ulid import ULID

__all__ = ["InvalidPlanAction", "PlanBuilder", "closed_actions"]


def closed_actions() -> dict[str, Any]:
    """Return the §8.4 closed vocabulary of plan actions.

    Imported lazily: ``app.agents.pipeline.tool_dispatch`` imports the tool
    registry, and planning must not depend on it at import time.
    """
    from app.agents.pipeline.tool_dispatch import ACTIONS

    return ACTIONS


class InvalidPlanAction(ValidationError):
    """Raised when a plan step names an action outside the §8.4 vocabulary.

    Attributes:
        action: The refused action (``""`` when the step declared none).
        order: The 1-based position of the offending step, when known.
        allowed: The vocabulary the plan was checked against.
    """

    def __init__(
        self,
        action: str,
        *,
        order: int | None = None,
        allowed: Sequence[str] = (),
    ) -> None:
        self.action = str(action or "")
        self.order = order
        self.allowed = tuple(allowed)
        position = f"L'étape {order} " if order else "Une étape "
        name = self.action or "<absente>"
        super().__init__(
            f"{position}déclare l'action '{name}', hors du vocabulaire fermé du "
            f"planificateur (§8.4). Actions admises : {', '.join(self.allowed)}. "
            "Aucune action de substitution n'est choisie (§0.2)."
        )


class PlanBuilder:
    """Build the plan structure defined in INIS section 8.2."""

    def build(
        self,
        request_id: str,
        objective: str,
        steps: list[dict[str, Any]],
        budget: dict[str, int | float | None],
    ) -> dict[str, Any]:
        """Return a complete plan with generated plan and step identifiers.

        Raises:
            InvalidPlanAction: When any step names an action outside the §8.4
                vocabulary. The plan is refused **before** anything is built, so
                a caller never receives a partially valid plan.
        """
        self.validate_steps(steps)
        return {
            "plan_id": ULID.new("PLAN_"),
            "request_id": request_id,
            "objective": objective,
            "steps": [
                self._build_step(step, order)
                for order, step in enumerate(steps, start=1)
            ],
            "budget": {
                "max_iterations": budget["max_iterations"],
                "max_cost": budget["max_cost"],
                "max_execution_time_seconds": budget["max_execution_time_seconds"],
            },
            "created_at": datetime.now(UTC).isoformat(timespec="microseconds").replace(
                "+00:00", "Z"
            ),
        }

    @classmethod
    def validate_steps(cls, steps: Sequence[Mapping[str, Any]]) -> list[str]:
        """Return the validated action of every step, or raise on the first bad one.

        Used on plans that must keep their identifiers — a plan submitted by a
        client, or one parsed from an LLM answer — where rebuilding the steps
        through :meth:`build` would renumber them.
        """
        return [
            cls.validate_step(step, order=order)
            for order, step in enumerate(steps, start=1)
        ]

    @staticmethod
    def validate_step(step: Mapping[str, Any], *, order: int | None = None) -> str:
        """Return the action of *step* once proven to belong to §8.4.

        Args:
            step: One plan step; ``action`` is the only field read here.
            order: 1-based position of the step, used in the refusal message.

        Returns:
            The validated action name.

        Raises:
            InvalidPlanAction: When the step is not a mapping, declares no
                action, or names one the pipeline does not know.
        """
        vocabulary = closed_actions()
        raw = step.get("action") if isinstance(step, Mapping) else None
        action = str(raw or "")
        if action not in vocabulary:
            raise InvalidPlanAction(action, order=order, allowed=sorted(vocabulary))
        return action

    @staticmethod
    def _build_step(step: dict[str, Any], order: int) -> dict[str, Any]:
        """Normalize a selected step to the section 8.2 delivery structure."""
        return {
            "step_id": ULID.new("STEP_"),
            "order": order,
            "action": step["action"],
            "tool": step["tool"],
            "inputs": step.get("inputs", {}),
            "expected_output": step["expected_output"],
            "status": step.get("status", "pending"),
            "depends_on": step.get("depends_on", []),
        }
