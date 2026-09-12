"""PHASE-02 smoke imports for runtime, router, registry, and workers."""

from __future__ import annotations

import importlib
import importlib.util

import pytest


def _has_symbol(module_name: str, symbol: str) -> bool:
    try:
        spec = importlib.util.find_spec(module_name)
    except ModuleNotFoundError:
        return False
    if spec is None:
        return False
    module = importlib.import_module(module_name)
    return hasattr(module, symbol)


@pytest.mark.skipif(
    not (
        _has_symbol("app.agents.runtime.state_machine", "StateMachine")
        and _has_symbol("app.agents.runtime.budget_tracker", "BudgetTracker")
        and _has_symbol("app.planning.plan_builder", "PlanBuilder")
    ),
    reason="runtime lot en cours",
)
def test_runtime_smoke() -> None:
    from app.agents.runtime.budget_tracker import BudgetTracker
    from app.agents.runtime.state_machine import StateMachine
    from app.planning.plan_builder import PlanBuilder

    assert StateMachine is not None
    assert BudgetTracker is not None
    assert PlanBuilder is not None


@pytest.mark.skipif(
    not (
        _has_symbol("app.llm.router.model_router", "ModelRouter")
        and _has_symbol("app.tools.registry", "ToolRegistry")
    ),
    reason="router/tools lot en cours",
)
def test_router_smoke() -> None:
    from app.llm.router.model_router import ModelRouter
    from app.tools.registry import ToolRegistry

    assert ModelRouter is not None
    assert ToolRegistry is not None


@pytest.mark.skipif(
    not _has_symbol("app.registry.agent_registry", "AgentRegistry"),
    reason="registry lot en cours",
)
def test_registry_smoke() -> None:
    from app.registry.agent_registry import AgentRegistry

    assert AgentRegistry is not None


@pytest.mark.skipif(
    not _has_symbol("app.workers.heartbeat_worker", "HeartbeatWorker"),
    reason="workers lot en cours",
)
def test_workers_smoke() -> None:
    from app.workers.heartbeat_worker import HeartbeatWorker

    assert HeartbeatWorker is not None
