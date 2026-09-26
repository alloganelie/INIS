"""Unit tests for BudgetTracker per §8."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.runtime.budget_tracker import BudgetTracker


def test_budget_tracker_initial_state_can_continue() -> None:
    tracker = BudgetTracker(
        max_iterations=5,
        max_cost=10.0,
        max_execution_time_seconds=60,
    )
    assert tracker.can_continue() is True
    assert tracker.iterations == 0
    assert tracker.cost == 0.0


def test_budget_tracker_stops_on_max_iterations() -> None:
    tracker = BudgetTracker(
        max_iterations=2,
        max_cost=None,
        max_execution_time_seconds=60,
    )
    assert tracker.can_continue() is True
    tracker.consume_iteration()
    assert tracker.can_continue() is True
    tracker.consume_iteration()
    assert tracker.can_continue() is False


def test_budget_tracker_stops_on_max_cost() -> None:
    tracker = BudgetTracker(
        max_iterations=10,
        max_cost=1.5,
        max_execution_time_seconds=60,
    )
    tracker.consume_cost(1.0)
    assert tracker.can_continue() is True
    tracker.consume_cost(0.5)
    assert tracker.can_continue() is False


def test_budget_tracker_unlimited_cost_allows_continuation() -> None:
    tracker = BudgetTracker(
        max_iterations=10,
        max_cost=None,
        max_execution_time_seconds=60,
    )
    tracker.consume_cost(9999.0)
    assert tracker.can_continue() is True


def test_budget_tracker_usage_snapshot() -> None:
    tracker = BudgetTracker(
        max_iterations=5,
        max_cost=10.0,
        max_execution_time_seconds=60,
        request_id="REQ_123",
    )
    tracker.consume_iteration()
    tracker.consume_cost(0.42)
    snap = tracker.get_usage_snapshot()
    assert snap["iterations"] == 1
    assert snap["cost_usd"] == 0.42
    assert "timestamp" in snap
    assert snap["timestamp"].endswith("Z")


@pytest.mark.asyncio
async def test_budget_tracker_persist_usage_noops_on_none_engine() -> None:
    tracker = BudgetTracker(max_iterations=1, max_cost=None, max_execution_time_seconds=10, request_id="REQ_1")
    await tracker.persist_usage(None)  # Must not raise
