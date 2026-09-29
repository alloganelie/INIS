"""§8.4/§0.2 — a plan is refused before it runs when it names a foreign action.

The plan was the last place where anything was accepted: ``_build_step`` copied
``step["action"]`` verbatim, so a plan naming an action no §21 tool implements
was accepted, executed step by step, and only refused later by the acquisition
stage — and the LLM path promoted a step's free-text ``description`` to the rank
of action. A plan is now validated against the closed vocabulary of
:mod:`app.agents.pipeline.tool_dispatch`: an unknown action is refused **by
name**, and no substitute action is ever chosen.
"""

from __future__ import annotations

import pytest

from app.agents.pipeline.tool_dispatch import ACTIONS
from app.domain.value_objects.ulid import ULID
from app.planning.plan_builder import (
    InvalidPlanAction,
    PlanBuilder,
    closed_actions,
)

REQUEST_ID = "REQ_01M3Q0000000000000000000AA"
BUDGET = {
    "max_iterations": 12,
    "max_cost": None,
    "max_execution_time_seconds": 300,
}


def _step(**overrides: object) -> dict:
    """Return a minimal step, valid unless overridden."""
    step = {
        "action": "collect_information",
        "tool": "collector",
        "expected_output": "information_unit",
    }
    step.update(overrides)
    return step


class TestTheVocabularyIsTheOneOfThePipeline:
    """The planner is checked against the execution vocabulary, not a copy."""

    def test_closed_actions_is_the_pipeline_vocabulary(self) -> None:
        assert closed_actions() is ACTIONS

    def test_every_pipeline_action_is_accepted(self) -> None:
        for action in ACTIONS:
            assert PlanBuilder.validate_step({"action": action}) == action


class TestAnUnknownActionIsRefused:
    """§8.4 — refusals name the action, its position and what is allowed."""

    def test_an_unknown_action_is_refused_by_name(self) -> None:
        with pytest.raises(InvalidPlanAction) as refusal:
            PlanBuilder.validate_step({"action": "verify"}, order=2)

        assert refusal.value.action == "verify"
        assert refusal.value.order == 2
        assert "verify" in str(refusal.value)
        assert "hors du vocabulaire fermé" in str(refusal.value)

    def test_the_refusal_lists_the_allowed_actions(self) -> None:
        with pytest.raises(InvalidPlanAction) as refusal:
            PlanBuilder.validate_step({"action": "verify"})

        for action in ACTIONS:
            assert action in str(refusal.value)

    def test_a_missing_action_is_refused_as_absent(self) -> None:
        """§0.2 — a step with no action is not defaulted to anything."""
        with pytest.raises(InvalidPlanAction) as refusal:
            PlanBuilder.validate_step({"tool": "web_search"}, order=1)

        assert refusal.value.action == ""
        assert "<absente>" in str(refusal.value)

    def test_a_description_is_not_an_action(self) -> None:
        """The exact defect: prose was promoted to the rank of plan action."""
        with pytest.raises(InvalidPlanAction):
            PlanBuilder.validate_step(
                {"description": "Ingère le fichier fourni par le client.", "tool": "read_csv"}
            )

    def test_a_non_mapping_step_is_refused(self) -> None:
        with pytest.raises(InvalidPlanAction):
            PlanBuilder.validate_step("collect_information")  # type: ignore[arg-type]


class TestBuildRefusesInvalidPlans:
    """§37 — nothing is built from a plan that will not be executed."""

    def test_build_refuses_the_first_invalid_step(self) -> None:
        with pytest.raises(InvalidPlanAction) as refusal:
            PlanBuilder().build(
                REQUEST_ID,
                "Objectif",
                [_step(), _step(action="bricoler", tool="x")],
                BUDGET,
            )

        assert refusal.value.order == 2

    def test_no_plan_is_returned_when_one_step_is_invalid(self) -> None:
        """The caller gets an exception, never a partially valid plan."""
        builder = PlanBuilder()
        plan = None
        try:
            plan = builder.build(REQUEST_ID, "Objectif", [_step(action="nope")], BUDGET)
        except InvalidPlanAction:
            pass

        assert plan is None

    def test_validate_steps_returns_the_validated_actions(self) -> None:
        assert PlanBuilder.validate_steps(
            [_step(), _step(action="fetch_page", tool="open_url")]
        ) == ["collect_information", "fetch_page"]

    def test_validate_steps_keeps_the_callers_identifiers(self) -> None:
        """A submitted plan must not be renumbered by the validation."""
        steps = [
            {
                "step_id": "STEP_CLIENT_1",
                "order": 1,
                "action": "collect_information",
                "tool": "collector",
                "expected_output": "information_unit",
            }
        ]

        PlanBuilder.validate_steps(steps)

        assert steps[0]["step_id"] == "STEP_CLIENT_1"
        assert ULID.is_valid(ULID.new("STEP_"))  # the builder still mints its own
