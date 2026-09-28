"""§28 request cycle tests: canonical stage list, activation, execution."""

from __future__ import annotations

import pytest

from app.core.errors import ValidationError
from app.planning.request_cycle import CYCLE_STAGES, RequestCycle, StageOutcome

#: The exact §28 ordering from INIS_SPEC.md — the spec pin.
SPEC_28_STAGES: tuple[str, ...] = (
    "RECEIVING",
    "AUTHENTICATION",
    "AUTHORIZATION",
    "UNDERSTANDING",
    "REQUIREMENT_EXTRACTION",
    "MEMORY_CHECK",
    "PLAN_GENERATION",
    "TOOL_SOURCE_DISCOVERY",
    "DATA_ACQUISITION",
    "EXTRACTION",
    "NORMALIZATION",
    "QUALITY_CONTROL",
    "SOURCE_CROSS_CHECK",
    "CONFIDENCE_ASSESSMENT",
    "CONTRADICTION_HANDLING",
    "AGENT_DELEGATION",
    "TARGETED_EXTRACTION",
    "RESULT_PACKAGING",
    "PERMISSION_CHECK",
    "DELIVERY",
    "AUDIT",
    "LEARNING_TELEMETRY",
)


def test_cycle_stages_match_spec_28_exactly() -> None:
    """The 22 §28 stages, in spec order."""
    assert CYCLE_STAGES == SPEC_28_STAGES
    assert len(CYCLE_STAGES) == 22


def test_cycle_requires_request_id() -> None:
    with pytest.raises(ValidationError):
        RequestCycle("")


def test_unknown_activated_stage_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RequestCycle("REQ_1", activated=["RECEIVING", "NOT_A_STAGE"])


def test_activation_defaults_to_all_stages_and_preserves_spec_order() -> None:
    cycle = RequestCycle("REQ_1")
    assert cycle.activated == CYCLE_STAGES
    cycle.deactivate("AUDIT", "LEARNING_TELEMETRY")
    assert cycle.activated == CYCLE_STAGES[:-2]
    cycle.activate("AUDIT")
    assert cycle.activated == CYCLE_STAGES[:-1]


class TestRun:
    @pytest.mark.asyncio
    async def test_runs_only_activated_stages_in_spec_order(self) -> None:
        cycle = RequestCycle("REQ_1", activated=["DELIVERY", "RECEIVING", "AUDIT"])
        executed: list[str] = []

        async def make_handler(stage: str):
            async def handler(cycle: RequestCycle) -> str:
                executed.append(stage)
                return f"done:{stage}"

            return handler

        handlers = {}
        for stage in ("RECEIVING", "DELIVERY", "AUDIT", "NORMALIZATION"):
            handlers[stage] = await make_handler(stage)

        outcomes = await cycle.run(handlers)
        assert executed == ["RECEIVING", "DELIVERY", "AUDIT"]
        assert [o.stage for o in outcomes] == ["RECEIVING", "DELIVERY", "AUDIT"]
        assert all(o.status == "completed" for o in outcomes)
        assert outcomes[0].result == "done:RECEIVING"
        assert all(isinstance(o, StageOutcome) for o in outcomes)

    @pytest.mark.asyncio
    async def test_activated_stage_without_handler_fails_fast(self) -> None:
        cycle = RequestCycle("REQ_1", activated=["RECEIVING", "AUDIT"])

        async def receiving(cycle: RequestCycle) -> None:
            return None

        with pytest.raises(ValidationError):
            await cycle.run({"RECEIVING": receiving})

    @pytest.mark.asyncio
    async def test_handler_failure_is_recorded_then_reraised(self) -> None:
        cycle = RequestCycle("REQ_1", activated=["RECEIVING", "DELIVERY"])

        async def receiving(cycle: RequestCycle) -> None:
            raise RuntimeError("source exploded")

        async def delivery(cycle: RequestCycle) -> None:  # pragma: no cover
            raise AssertionError("must not run after failure")

        with pytest.raises(RuntimeError):
            await cycle.run({"RECEIVING": receiving, "DELIVERY": delivery})
        assert len(cycle.outcomes) == 1
        assert cycle.outcomes[0].status == "failed"
        assert "source exploded" in (cycle.outcomes[0].error or "")

    @pytest.mark.asyncio
    async def test_unknown_handler_stage_is_rejected(self) -> None:
        cycle = RequestCycle("REQ_1", activated=["RECEIVING"])

        async def receiving(cycle: RequestCycle) -> None:
            return None

        with pytest.raises(ValidationError):
            await cycle.run({"RECEIVING": receiving, "BOGUS": receiving})
