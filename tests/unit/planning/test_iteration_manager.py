"""Tests for IterationManager lifecycle and decision-making."""

import pytest

from app.planning.iteration_manager import IterationManager


@pytest.fixture
def iteration_manager():
    """Create an IterationManager instance for testing."""
    return IterationManager()


def test_start_iteration_structure(iteration_manager):
    """Test creating a new iteration with proper structure per §8.3."""
    iteration = iteration_manager.start_iteration(
        request_id="REQ_123",
        iteration_number=1,
        objective="Test objective",
        hypothesis="Test hypothesis",
    )

    assert iteration["iteration_id"].startswith("ITER_")
    assert iteration["request_id"] == "REQ_123"
    assert iteration["iteration_number"] == 1
    assert iteration["objective"] == "Test objective"
    assert iteration["hypothesis"] == "Test hypothesis"
    assert iteration["decision"] == "continue"
    assert iteration["termination_reason"] is None
    assert iteration["actions"] == []
    assert iteration["tools_used"] == []
    assert iteration["inputs"] == []
    assert iteration["outputs"] == []
    assert iteration["new_evidence"] == []


def test_complete_iteration_and_decision(iteration_manager):
    """Test completing an iteration with decision and §8.5 continuation criteria."""
    iteration = iteration_manager.start_iteration(
        request_id="REQ_123",
        iteration_number=1,
        objective="Test objective",
    )
    
    # Test completion
    completed = iteration_manager.complete_iteration(
        iteration,
        decision="stop",
        termination_reason="Requirements satisfied",
    )
    assert completed["decision"] == "stop"
    assert completed["termination_reason"] == "Requirements satisfied"

    # Test continuation criteria
    # Should continue when no criteria are met
    assert iteration_manager.should_continue(iteration) is True

    # Should stop when requirements are satisfied
    assert iteration_manager.should_continue(
        iteration, requirements_satisfied=True
    ) is False

    # Should stop when confidence threshold is met
    assert iteration_manager.should_continue(
        iteration, confidence_score=0.9, minimum_confidence=0.8
    ) is False

    # Should stop when budget is exhausted
    assert iteration_manager.should_continue(
        iteration, budget_exhausted=True
    ) is False


def test_record_iteration_data(iteration_manager):
    """Test recording actions, tools, and evidence during iteration."""
    iteration = iteration_manager.start_iteration(
        request_id="REQ_123",
        iteration_number=1,
        objective="Test objective",
    )
    
    # Record action
    iteration_manager.record_action(
        iteration,
        action="web_search",
        tool="search_tool",
        inputs={"query": "test"},
    )
    assert len(iteration["actions"]) == 1
    assert iteration["actions"][0]["action"] == "web_search"

    # Record tool usage
    iteration_manager.record_tool_usage(iteration, "search_tool")
    iteration_manager.record_tool_usage(iteration, "api_tool")
    assert len(iteration["tools_used"]) == 2

    # Record evidence
    iteration_manager.record_evidence(iteration, "EVID_001")
    iteration_manager.record_evidence(iteration, "EVID_002")
    assert len(iteration["new_evidence"]) == 2
