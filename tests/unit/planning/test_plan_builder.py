"""Tests for the INIS plan builder."""

from app.domain.value_objects.ulid import ULID
from app.planning.plan_builder import PlanBuilder


def build_plan() -> dict:
    return PlanBuilder().build(
        request_id="REQ_01H00000000000000000000000",
        objective="Verify a source",
        steps=[
            {
                "action": "search",
                "tool": "web_search",
                "inputs": {"query": "INIS"},
                "expected_output": "sources",
            },
            {
                "action": "verify",
                "tool": "evidence_checker",
                "expected_output": "evidence",
                "depends_on": ["STEP_01H00000000000000000000000"],
            },
        ],
        budget={
            "max_iterations": 12,
            "max_cost": 10.0,
            "max_execution_time_seconds": 300,
        },
    )


def test_plan_builder_returns_section_8_2_structure() -> None:
    plan = build_plan()

    assert set(plan) == {
        "plan_id",
        "request_id",
        "objective",
        "steps",
        "budget",
        "created_at",
    }
    assert ULID.is_valid(plan["plan_id"])
    assert plan["created_at"].endswith("Z")


def test_plan_builder_generates_ordered_step_identifiers() -> None:
    plan = build_plan()

    assert [step["order"] for step in plan["steps"]] == [1, 2]
    assert all(ULID.is_valid(step["step_id"]) for step in plan["steps"])


def test_plan_builder_preserves_step_and_budget_details() -> None:
    plan = build_plan()

    assert plan["steps"][0]["inputs"] == {"query": "INIS"}
    assert plan["steps"][1]["depends_on"] == ["STEP_01H00000000000000000000000"]
    assert plan["budget"] == {
        "max_iterations": 12,
        "max_cost": 10.0,
        "max_execution_time_seconds": 300,
    }
