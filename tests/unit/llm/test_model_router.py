"""Tests for ModelRouter per INIS spec §22."""

from app.llm.router.model_router import ModelRouter


def test_model_router_basic_routing() -> None:
    """Test basic routing based on task type."""
    router = ModelRouter()
    assert router.route("reasoning") == "openai/gpt-4"
    assert router.route("extraction") == "openai/gpt-3.5-turbo"
    assert router.route("planning") == "openai/gpt-4"


def test_model_router_cost_budget_does_not_override_configured_model() -> None:
    """Test budgets do not bypass the configured model selection."""
    router = ModelRouter()
    assert router.route("reasoning", cost_budget=0.005) == "openai/gpt-4"
    assert router.route("reasoning", cost_budget=0.02) == "openai/gpt-4"


def test_model_router_latency_budget_does_not_override_configured_model() -> None:
    """Test latency budgets do not bypass the configured model selection."""
    router = ModelRouter()
    assert router.route("reasoning", latency_budget=0.5) == "openai/gpt-4"
    assert router.route("reasoning", latency_budget=2.0) == "openai/gpt-4"


def test_model_router_unknown_task_uses_default() -> None:
    """Test that unknown task types fall back silently to the default model."""
    router = ModelRouter()
    assert router.route("unknown_task") == "openai/gpt-3.5-turbo"
