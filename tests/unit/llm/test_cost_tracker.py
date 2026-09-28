"""Unit tests for CostTracker per §22 and §38."""

import pytest

from app.llm.router.cost_tracker import CostTracker


def test_cost_tracker_initial_state() -> None:
    tracker = CostTracker()
    assert tracker.get_all_costs() == {}
    assert tracker.get_total_cost("gpt-4") == 0.0
    assert tracker.pending_usage() == []


def test_cost_tracker_record_cost() -> None:
    tracker = CostTracker()
    tracker.record_cost("gpt-4", 0.05)
    tracker.record_cost("gpt-4", 0.02)
    assert tracker.get_total_cost("gpt-4") == pytest.approx(0.07)


def test_cost_tracker_negative_cost_raises() -> None:
    tracker = CostTracker()
    with pytest.raises(ValueError, match="Cost cannot be negative"):
        tracker.record_cost("gpt-4", -0.01)


def test_cost_tracker_record_usage() -> None:
    tracker = CostTracker()
    entry = tracker.record_usage(
        model_id="claude-3",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.003,
    )
    assert entry.model_id == "claude-3"
    assert entry.input_tokens == 100
    assert entry.output_tokens == 50
    assert entry.cost_usd == 0.003
    assert tracker.get_total_cost("claude-3") == pytest.approx(0.003)
    assert len(tracker.pending_usage()) == 1


def test_cost_tracker_negative_tokens_raise() -> None:
    tracker = CostTracker()
    with pytest.raises(ValueError, match="Token counts cannot be negative"):
        tracker.record_usage("gpt-4", input_tokens=-10)


def test_cost_tracker_reset() -> None:
    tracker = CostTracker()
    tracker.record_usage("gpt-4", 10, 10, 0.01)
    tracker.reset()
    assert tracker.get_all_costs() == {}
    assert tracker.pending_usage() == []
