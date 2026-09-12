"""Tests for ModelRouter per INIS spec §22."""

import pytest

from app.llm.router.model_router import ModelRouter


def test_model_router_basic_routing() -> None:
    """Test basic routing based on task type."""
    router = ModelRouter()
    assert router.route("reasoning") == "gpt-4"
    assert router.route("extraction") == "gpt-3.5-turbo"
    assert router.route("planning") == "gpt-4"


def test_model_router_cost_budget() -> None:
    """Test routing with cost budget constraints."""
    router = ModelRouter()
    assert router.route("reasoning", cost_budget=0.005) == "gpt-3.5-turbo"
    assert router.route("reasoning", cost_budget=0.02) == "gpt-4"


def test_model_router_latency_budget() -> None:
    """Test routing with latency budget constraints."""
    router = ModelRouter()
    assert router.route("reasoning", latency_budget=0.5) == "gpt-3.5-turbo"
    assert router.route("reasoning", latency_budget=2.0) == "gpt-4"


def test_model_router_unknown_task() -> None:
    """Test that unknown task types raise ValueError."""
    router = ModelRouter()
    with pytest.raises(ValueError, match="Unknown task type"):
        router.route("unknown_task")
