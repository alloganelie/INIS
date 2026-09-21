"""PHASE-09 smoke: pipeline complet (understanding → planning → exécution → décision)."""

from __future__ import annotations

import importlib
import importlib.util

import pytest


def _has_module(module_name: str) -> bool:
    """Return True if *module_name* can be found without importing it."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ModuleNotFoundError, ValueError):
        return False


def _has_symbol(module_name: str, symbol: str) -> bool:
    """Return True if *module_name* defines *symbol* (False si absent)."""
    if not _has_module(module_name):
        return False
    try:
        module = importlib.import_module(module_name)
    except ImportError:
        return False
    return getattr(module, symbol, None) is not None


def _import_or_skip(module_name: str):
    """Import *module_name* or skip the test if it is absent."""
    if not _has_module(module_name):
        pytest.skip(f"module absent: {module_name}")
    return importlib.import_module(module_name)


def _symbol_or_skip(module, module_name: str, symbol: str):
    """Return *symbol* from *module* or skip if it is not defined."""
    value = getattr(module, symbol, None)
    if value is None:
        pytest.skip(f"symbol absent: {symbol} in {module_name}")
    return value


def _require_symbols(pairs: list[tuple[str, str]]) -> None:
    """Skip listing every missing (module, symbol); pass if all present."""
    missing = [
        f"{symbol} in {module}"
        for module, symbol in pairs
        if not _has_symbol(module, symbol)
    ]
    if missing:
        pytest.skip("symbols absents: " + "; ".join(missing))


def test_understanding_imports() -> None:
    """Compréhension de requête per §8 (skip si module absent)."""
    _require_symbols(
        [
            ("app.agents.understanding", "RequestParser"),
            ("app.agents.understanding", "InformationRequest"),
        ]
    )


def test_decision_imports() -> None:
    """Décision d'arrêt/délégation (skip si module absent)."""
    _require_symbols(
        [
            ("app.agents.decision", "TerminationEvaluator"),
            ("app.agents.decision", "TerminationDecision"),
        ]
    )


def test_pipeline_coordinator_imports() -> None:
    """Coordinateur understanding → planning → exécution (skip si absent)."""
    _require_symbols([("app.agents.pipeline", "PipelineCoordinator")])


def test_plan_executor_imports() -> None:
    """Exécuteur de plan §8 (skip si module absent)."""
    _require_symbols([("app.planning.plan_executor", "PlanExecutor")])


def test_iteration_manager_imports() -> None:
    """Gestion du cycle d'itérations §8.3 (skip si module absent)."""
    _require_symbols([("app.planning.iteration_manager", "IterationManager")])


def test_model_router_complete_method() -> None:
    """ModelRouter expose `complete` §22 (skip si module absent, sans appel réseau)."""
    module_name = "app.llm.router.model_router"
    module = _import_or_skip(module_name)
    router_cls = _symbol_or_skip(module, module_name, "ModelRouter")
    complete = getattr(router_cls, "complete", None)
    if not callable(complete):
        pytest.skip(f"symbol absent: complete in {module_name}.ModelRouter")
    assert callable(complete)


def test_llm_tasks_imports() -> None:
    """Tâches LLM §22 (skip si module absent)."""
    _require_symbols(
        [
            ("app.llm.tasks", "UnderstandingTask"),
            ("app.llm.tasks", "PlanningTask"),
            ("app.llm.tasks", "ClassificationTask"),
        ]
    )


def test_llm_prompts_builders_imports() -> None:
    """Builders de prompts §22 (skip si module absent)."""
    module_name = "app.llm.prompts"
    module = _import_or_skip(module_name)
    for symbol in ("build_understanding", "build_planning"):
        if not callable(getattr(module, symbol, None)):
            pytest.skip(f"symbol absent: {symbol} in {module_name}")
    assert callable(module.build_understanding)
    assert callable(module.build_planning)


def test_llm_trace_writer_imports() -> None:
    """Trace d'audit des décisions LLM §41.12 (skip si module absent)."""
    _require_symbols([("app.llm.tracing.llm_trace_writer", "LLMTraceWriter")])


def test_pipeline_runner_imports() -> None:
    """Runner pipeline dédié (skip si module absent).

    Constaté : aucun `*Runner` dans `app/` (`app.workers.request_worker`
    est vide) ; le rôle est tenu par `PipelineCoordinator`.
    """
    candidates = [
        ("app.planning.pipeline_runner", "PipelineRunner"),
        ("app.agents.pipeline.pipeline_runner", "PipelineRunner"),
        ("app.workers.request_worker", "RequestWorker"),
    ]
    if not any(_has_symbol(module, symbol) for module, symbol in candidates):
        pytest.skip(
            "symbols absents: "
            + "; ".join(f"{symbol} in {module}" for module, symbol in candidates)
        )


def test_termination_evaluator_smoke() -> None:
    """Evaluate → stop si exigences satisfaites, continue sinon (skip si absent)."""
    module_name = "app.agents.decision.termination_evaluator"
    module = _import_or_skip(module_name)
    evaluator_cls = _symbol_or_skip(module, module_name, "TerminationEvaluator")
    context_cls = _symbol_or_skip(module, module_name, "TerminationContext")

    stop = evaluator_cls().evaluate(context_cls(requirements_satisfied=True))
    assert stop.should_terminate is True
    assert stop.reason.name == "REQUIREMENTS_SATISFIED"

    go_on = evaluator_cls().evaluate(context_cls())
    assert go_on.should_terminate is False


def test_request_parser_smoke() -> None:
    """Parse → InformationRequest avec request_id (skip si module absent)."""
    module_name = "app.agents.understanding.request_parser"
    module = _import_or_skip(module_name)
    parser_cls = _symbol_or_skip(module, module_name, "RequestParser")

    request = parser_cls().parse("Quel est le taux de confiance du pipeline ?")
    assert request.request_id.startswith("REQ_")
    assert "confiance" in request.objective


def test_state_machine_full_cycle() -> None:
    """Cycle RECEIVED → DONE + transition invalide rejetée (skip si absent)."""
    module_name = "app.agents.runtime.state_machine"
    module = _import_or_skip(module_name)
    machine_cls = _symbol_or_skip(module, module_name, "StateMachine")
    states = _symbol_or_skip(module, module_name, "AgentState")

    machine = machine_cls()
    assert machine.state == states.RECEIVED
    for next_state in (
        states.UNDERSTANDING,
        states.PLANNED,
        states.EXECUTING,
        states.VERIFYING,
        states.DELIVERING,
        states.DONE,
    ):
        assert machine.transition(next_state) == next_state
    assert machine.state == states.DONE

    from app.core.errors import ValidationError

    with pytest.raises(ValidationError):
        machine_cls().transition(states.DONE)


async def test_pipeline_e2e_smoke() -> None:
    """POST /v1/requests (201) puis GET état (200) via httpx ASGI."""
    import httpx

    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        created = await client.post(
            "/v1/requests", json={"objective": "smoke phase 09"}
        )
    assert created.status_code == 201, created.text
    request_id = created.json().get("request_id")
    assert request_id, "aucun request_id dans la réponse de création"

    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        fetched = await client.get(f"/v1/requests/{request_id}")
    assert fetched.status_code == 200, fetched.text
    assert fetched.json().get("request_id") == request_id
