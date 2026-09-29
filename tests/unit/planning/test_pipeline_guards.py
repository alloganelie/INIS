"""Unit tests for the §41.13 execution complexity safeguards.

Verifies:
1. Threshold configuration (:func:`max_plan_steps`, :func:`max_parallel_tool_calls`,
   and :func:`exceeds_plan_limit`) including environment overrides and fallback safety.
2. :class:`ConcurrencyLimiter` concurrency bounding, peak-watermark tracking,
   failure cleanup, and §34 metrics reporting.
3. :class:`PipelineRunner` integration with planning guards: rejection on plans
   exceeding ``MAX_PLAN_STEPS``, gate allocation, and post-run reset.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.planning.limits import (
    DEFAULT_MAX_PARALLEL_TOOL_CALLS,
    DEFAULT_MAX_PLAN_STEPS,
    PLANNING_LIMIT_EXCEEDED_STATUS,
    ConcurrencyLimiter,
    exceeds_plan_limit,
    max_parallel_tool_calls,
    max_plan_steps,
)


class TestLimitsConfiguration:
    """§41.13 — verification of configurable guard limits."""

    def test_default_constants(self) -> None:
        """Default thresholds match the §41.13 specification."""
        assert DEFAULT_MAX_PLAN_STEPS == 50
        assert DEFAULT_MAX_PARALLEL_TOOL_CALLS == 10
        assert PLANNING_LIMIT_EXCEEDED_STATUS == "PLANNING_LIMIT_EXCEEDED"

    def test_defaults_when_env_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When environment variables are absent, defaults are returned."""
        monkeypatch.delenv("MAX_PLAN_STEPS", raising=False)
        monkeypatch.delenv("MAX_PARALLEL_TOOL_CALLS", raising=False)
        assert max_plan_steps() == DEFAULT_MAX_PLAN_STEPS
        assert max_parallel_tool_calls() == DEFAULT_MAX_PARALLEL_TOOL_CALLS

    def test_custom_env_values(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Environment variables override the default values."""
        monkeypatch.setenv("MAX_PLAN_STEPS", "25")
        monkeypatch.setenv("MAX_PARALLEL_TOOL_CALLS", "4")
        assert max_plan_steps() == 25
        assert max_parallel_tool_calls() == 4

    @pytest.mark.parametrize(
        "bad_value",
        ["0", "-1", "-42", "not_an_int", "   ", ""],
    )
    def test_invalid_env_falls_back_to_defaults(
        self, monkeypatch: pytest.MonkeyPatch, bad_value: str
    ) -> None:
        """Unusable or non-positive values fall back safely to defaults."""
        monkeypatch.setenv("MAX_PLAN_STEPS", bad_value)
        monkeypatch.setenv("MAX_PARALLEL_TOOL_CALLS", bad_value)
        assert max_plan_steps() == DEFAULT_MAX_PLAN_STEPS
        assert max_parallel_tool_calls() == DEFAULT_MAX_PARALLEL_TOOL_CALLS

    def test_exceeds_plan_limit_evaluation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """``exceeds_plan_limit`` accurately detects threshold violations."""
        monkeypatch.setenv("MAX_PLAN_STEPS", "10")
        assert not exceeds_plan_limit(5)
        assert not exceeds_plan_limit(10)
        assert exceeds_plan_limit(11)

        # Explicit limit overrides active environment
        assert not exceeds_plan_limit(11, limit=15)
        assert exceeds_plan_limit(11, limit=5)


class TestConcurrencyLimiter:
    """§41.13 — tool concurrency bounded by an async semaphore."""

    def test_initialization_defaults_and_explicit(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Limiter uses either explicit limit or active environment threshold."""
        monkeypatch.setenv("MAX_PARALLEL_TOOL_CALLS", "8")
        limiter = ConcurrencyLimiter()
        assert limiter.limit == 8
        assert limiter.active == 0
        assert limiter.peak_active == 0
        assert limiter.acquired == 0

        explicit = ConcurrencyLimiter(limit=3)
        assert explicit.limit == 3

    def test_enforces_minimum_limit_of_one(self) -> None:
        """Limiter refuses non-positive limits and clamps them to at least 1."""
        limiter = ConcurrencyLimiter(limit=0)
        assert limiter.limit == 1
        negative = ConcurrencyLimiter(limit=-5)
        assert negative.limit == 1

    async def test_bounds_peak_concurrency_under_load(self) -> None:
        """Observed peak active tasks never exceeds the configured limit."""
        limit = 3
        total_tasks = 12
        limiter = ConcurrencyLimiter(limit=limit)

        observed_peaks: list[int] = []

        async def _work(idx: int) -> int:
            observed_peaks.append(limiter.active)
            assert limiter.active <= limit
            await asyncio.sleep(0.01)
            return idx * 2

        tasks = [limiter.run(_work, i) for i in range(total_tasks)]
        results = await asyncio.gather(*tasks)

        assert results == [i * 2 for i in range(total_tasks)]
        assert limiter.active == 0
        assert limiter.acquired == total_tasks
        assert limiter.peak_active <= limit
        assert max(observed_peaks) <= limit

    async def test_decrements_active_counter_on_exception(self) -> None:
        """If a task fails, ``active`` is decremented in finally block."""
        limiter = ConcurrencyLimiter(limit=2)

        async def _failing() -> None:
            await asyncio.sleep(0.005)
            msg = "synthetic tool failure"
            raise RuntimeError(msg)

        with pytest.raises(RuntimeError, match="synthetic tool failure"):
            await limiter.run(_failing)

        assert limiter.active == 0
        assert limiter.acquired == 1

    def test_stats_matches_metrics_contract(self) -> None:
        """``stats()`` dictionary conforms to §34 metrics reporting schema."""
        limiter = ConcurrencyLimiter(limit=5)
        stats = limiter.stats()
        assert stats == {
            "limit": 5,
            "active": 0,
            "peak_active": 0,
            "acquired": 0,
        }


class TestPipelineRunnerLimitsWiring:
    """§41.13 — integration between limits guards and PipelineRunner."""

    async def test_runner_rejects_plan_exceeding_max_plan_steps(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A plan with more steps than MAX_PLAN_STEPS is immediately rejected."""
        monkeypatch.setenv("MAX_PLAN_STEPS", "3")
        runner = PipelineRunner()
        runner.reset_state()

        large_plan = {
            "plan_id": "PLAN_OVERSIZED",
            "steps": [
                {
                    "step_id": f"STEP_{i}",
                    # §8.4 — the plan is valid: this test is about §41.13, and an
                    # invalid action would be refused before the step count is read.
                    "action": "collect_information",
                    "tool": "collector",
                    "expected_output": "information_unit",
                    "inputs": {},
                }
                for i in range(5)
            ],
        }

        result = await runner.run(
            "REQ_OVERSIZED",
            {"objective": "test oversized plan", "plan": large_plan},
        )

        assert result["status"] == PLANNING_LIMIT_EXCEEDED_STATUS
        assert "exceeded safeguard threshold" in result["summary"]
        assert any("Plan rejected" in limit for limit in result["limitations"])
        assert result["confidence"]["score"] == 0.0
        assert result["information_units"] == []
        assert result["evidence"] == []

    async def test_runner_allocates_tool_gate_for_valid_plan(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A plan within limits initializes and exposes ``tool_gate()``."""
        monkeypatch.setenv("MAX_PLAN_STEPS", "10")
        monkeypatch.setenv("MAX_PARALLEL_TOOL_CALLS", "4")
        runner = PipelineRunner()
        runner.reset_state()

        normal_plan = {
            "plan_id": "PLAN_VALID",
            "steps": [
                {
                    "step_id": "STEP_1",
                    "action": "collect_information",
                    "tool": "collector",
                    "expected_output": "information_unit",
                    "inputs": {"query": "safe query"},
                }
            ],
        }

        result = await runner.run(
            "REQ_WITHIN_LIMITS",
            {"objective": "test within limits", "plan": normal_plan},
        )

        assert result["status"] != PLANNING_LIMIT_EXCEEDED_STATUS
        gate = runner.tool_gate()
        assert gate is not None
        assert isinstance(gate, ConcurrencyLimiter)
        assert gate.limit == 4

        # Resetting the runner clears the tool gate
        runner.reset_state()
        assert runner.tool_gate() is None

