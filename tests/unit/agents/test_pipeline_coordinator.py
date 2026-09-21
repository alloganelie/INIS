"""Tests for in-memory pipeline orchestration."""

from typing import Any

from app.agents.pipeline.pipeline_coordinator import PipelineCoordinator
from app.agents.runtime.state_machine import AgentState
from app.planning.plan_builder import PlanBuilder


class SuccessfulTool:
    def execute(self, step: dict[str, Any]) -> dict[str, Any]:
        return {"requirement": step["inputs"]["requirement"], "source_id": "SRC_TEST"}


def test_coordinator_runs_understanding_planning_execution_and_delivery() -> None:
    result = PipelineCoordinator().run(
        "Find current vaccination coverage in Benin",
        plan_builder=PlanBuilder(),
        tool=SuccessfulTool(),
    )

    assert result.state is AgentState.DONE
    assert result.plan is not None
    assert result.step_results[0]["status"] == "done"
    assert result.model_enrichment_skipped is True


def test_coordinator_stops_ambiguous_request_before_planning() -> None:
    result = PipelineCoordinator().run(
        "help",
        plan_builder=PlanBuilder(),
        tool=SuccessfulTool(),
    )

    assert result.state is AgentState.FAILED
    assert result.plan is None
    assert result.clarification_reasons
