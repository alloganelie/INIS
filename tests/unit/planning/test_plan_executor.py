"""Tests for PlanExecutor dependency resolution and execution."""

import pytest
from unittest.mock import AsyncMock

from app.planning.plan_executor import PlanExecutor, ExecutionResult


@pytest.fixture
def sample_plan():
    """Create a sample plan for testing."""
    return {
        "plan_id": "PLAN_123",
        "request_id": "REQ_456",
        "objective": "Test objective",
        "steps": [
            {
                "step_id": "STEP_001",
                "order": 1,
                "action": "test_action_1",
                "tool": "test_tool",
                "inputs": {},
                "expected_output": "result_1",
                "status": "pending",
                "depends_on": [],
            },
            {
                "step_id": "STEP_002",
                "order": 2,
                "action": "test_action_2",
                "tool": "test_tool",
                "inputs": {},
                "expected_output": "result_2",
                "status": "pending",
                "depends_on": ["STEP_001"],
            },
            {
                "step_id": "STEP_003",
                "order": 3,
                "action": "test_action_3",
                "tool": "test_tool",
                "inputs": {},
                "expected_output": "result_3",
                "status": "pending",
                "depends_on": ["STEP_002"],
            },
        ],
        "budget": {
            "max_iterations": 10,
            "max_cost": 100.0,
            "max_execution_time_seconds": 300,
        },
        "created_at": "2024-01-01T00:00:00Z",
    }


@pytest.mark.asyncio
async def test_execute_simple_plan(sample_plan):
    """Test execution of a simple plan with sequential dependencies."""
    executor = PlanExecutor()
    step_executor = AsyncMock(return_value={"result": "success"})

    result = await executor.execute(sample_plan, step_executor)

    assert result.success is True
    assert len(result.completed_steps) == 3
    assert len(result.failed_steps) == 0
    assert "STEP_001" in result.completed_steps
    assert "STEP_002" in result.completed_steps
    assert "STEP_003" in result.completed_steps


@pytest.mark.asyncio
async def test_execute_with_step_failure(sample_plan):
    """Test execution when a step fails and retries are exhausted."""
    executor = PlanExecutor()
    
    # Make STEP_002 fail
    async def failing_step_executor(step):
        if step["step_id"] == "STEP_002":
            raise Exception("Step failed")
        return {"result": "success"}
    
    result = await executor.execute(sample_plan, failing_step_executor, max_retries=2)

    assert result.success is False
    assert "STEP_001" in result.completed_steps
    assert "STEP_002" in result.failed_steps
    assert "STEP_003" not in result.completed_steps  # Blocked by failed dependency
    assert "failed after" in result.error.lower() and "retries" in result.error.lower()


@pytest.mark.asyncio
async def test_execute_with_retry_success(sample_plan):
    """Test execution when a step fails but succeeds on retry."""
    executor = PlanExecutor()
    call_count = {"STEP_002": 0}
    
    async def retrying_step_executor(step):
        if step["step_id"] == "STEP_002":
            call_count["STEP_002"] += 1
            if call_count["STEP_002"] < 2:
                raise Exception("Temporary failure")
        return {"result": "success"}
    
    result = await executor.execute(sample_plan, retrying_step_executor, max_retries=3)

    assert result.success is True
    assert len(result.completed_steps) == 3
    assert call_count["STEP_002"] == 2  # Failed once, succeeded on retry


@pytest.mark.asyncio
async def test_execute_with_circular_dependency():
    """Test execution fails with circular dependency detection."""
    executor = PlanExecutor()
    
    circular_plan = {
        "plan_id": "PLAN_123",
        "request_id": "REQ_456",
        "objective": "Test circular",
        "steps": [
            {
                "step_id": "STEP_001",
                "order": 1,
                "action": "test_action_1",
                "tool": "test_tool",
                "inputs": {},
                "expected_output": "result_1",
                "status": "pending",
                "depends_on": ["STEP_002"],
            },
            {
                "step_id": "STEP_002",
                "order": 2,
                "action": "test_action_2",
                "tool": "test_tool",
                "inputs": {},
                "expected_output": "result_2",
                "status": "pending",
                "depends_on": ["STEP_001"],
            },
        ],
        "budget": {"max_iterations": 10, "max_cost": 100.0, "max_execution_time_seconds": 300},
        "created_at": "2024-01-01T00:00:00Z",
    }
    
    step_executor = AsyncMock(return_value={"result": "success"})
    result = await executor.execute(circular_plan, step_executor)

    assert result.success is False
    assert "circular" in result.error.lower()
    assert len(result.completed_steps) == 0


@pytest.mark.asyncio
async def test_get_execution_progress(sample_plan):
    """Test execution progress calculation."""
    executor = PlanExecutor()
    
    # Execute first step only
    async def partial_executor(step):
        if step["step_id"] == "STEP_001":
            return {"result": "success"}
        raise Exception("Stop after first step")
    
    await executor.execute(sample_plan, partial_executor)
    
    progress = executor.get_execution_progress(sample_plan, {"STEP_001"})
    
    assert progress["total_steps"] == 3
    assert progress["completed_steps"] == 1
    assert progress["remaining_steps"] == 2
    assert progress["progress_percentage"] == pytest.approx(33.33, rel=0.1)
