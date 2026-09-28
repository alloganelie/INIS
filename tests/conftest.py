"""Global test fixtures shared by the whole INIS suite (§33.2).

Before B4-bis this file held a single circuit-breaker fixture, so every test
module re-invented its own database, Redis, web and LLM doubles — and the
process-wide ``PipelineRunner`` state leaked from one test file to the next.

The fixtures below are the shared contract:

* ``postgres_container`` / ``redis_container`` — re-exported from
  :mod:`tests.containers` so Docker-backed tests share one container per
  session;
* ``db_url`` — a migrated PostgreSQL database (``alembic upgrade head``);
* ``redis_url`` — a live Redis endpoint;
* ``reset_pipeline_state`` — autouse isolation of the ``PipelineRunner``
  singleton between tests;
* ``mock_llm`` — configurable ``ModelRouter.complete`` stub (§22);
* ``mock_web`` — default ``httpx.MockTransport`` for the §9/§10 connectors.
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest

from app.connectors.resilience.circuit_breaker import CircuitBreakerConfig
from app.connectors.resilience.circuit_breaker import registry as breaker_registry
from tests.containers import (  # noqa: F401 - fixtures re-exported for the suite
    MINIO_BUCKET,
    MINIO_ROOT_PASSWORD,
    MINIO_ROOT_USER,
    docker_available,
    minio_container,
    minio_endpoint,
    postgres_container,
    postgres_url,
    redis_container,
)
from tests.containers import redis_url as _redis_url_from_container
from tests.containers import run_alembic_upgrade


@pytest.fixture(autouse=True)
def _reset_circuit_breakers():
    """Isolate the process-wide §41.8 breaker registry between tests."""
    breaker_registry.reset(default_config=CircuitBreakerConfig())
    yield
    breaker_registry.reset(default_config=CircuitBreakerConfig())


@pytest.fixture(autouse=True)
def reset_pipeline_state():
    """Reset the ``PipelineRunner`` singleton stores before and after a test.

    ``pipeline_runner`` is a module-level instance, so ``_run_states``,
    ``_event_history``, ``_lifecycles`` and the counters accumulated by one
    test file used to be visible to the next one. Autouse: every test starts
    from a pristine runner.
    """
    from app.api.v1.requests.pipeline_runner import pipeline_runner

    pipeline_runner.reset_state()
    yield pipeline_runner
    pipeline_runner.reset_state()


@pytest.fixture(scope="session")
def db_url(postgres_container: Any) -> Iterator[str]:
    """Provide a migrated PostgreSQL URL for the session (§4.2, §27).

    The ``pgvector`` container is started once, ``alembic upgrade head`` is
    applied once, and every test consuming this fixture gets the real
    migration-created schema.
    """
    url = postgres_url(postgres_container)
    run_alembic_upgrade(url)
    yield url


@pytest.fixture(scope="session")
def redis_url(redis_container: Any) -> str:
    """Provide a live Redis endpoint for the session (§19, §41.5)."""
    return _redis_url_from_container(redis_container)



@pytest.fixture(scope="session")
def minio_url(minio_container: Any) -> str:
    """Provide a live MinIO endpoint for the session (§4.3)."""
    return minio_endpoint(minio_container)


class MockLLMControl:
    """Configurable stub driving ``ModelRouter.complete`` (§22).

    Attributes:
        content: Text returned by every ``complete`` call.
        stub: Value of ``LLMResponse.stub`` the stub reports.
        calls: ``(task, prompt)`` pairs recorded for assertions.
    """

    def __init__(self) -> None:
        self.content: str = ""
        self.stub: bool = False
        self.calls: list[tuple[Any, str]] = []

    def configure(self, content: str, *, stub: bool = False) -> "MockLLMControl":
        """Set the canned answer and return ``self`` for fluent use."""
        self.content = content
        self.stub = stub
        return self


@pytest.fixture
def mock_llm(monkeypatch: pytest.MonkeyPatch) -> MockLLMControl:
    """Replace ``ModelRouter.complete`` with a deterministic, configurable stub."""
    from app.llm.router import model_router as model_router_module

    control = MockLLMControl()

    async def _complete(self: Any, task: Any, prompt: str, **kwargs: Any) -> Any:
        control.calls.append((task, prompt))
        return model_router_module.LLMResponse(
            content=control.content,
            model="mock-llm",
            stub=control.stub,
        )

    monkeypatch.setattr(model_router_module.ModelRouter, "complete", _complete)
    return control


def default_web_handler(request: Any) -> Any:
    """Answer §9/§10 HTTP calls with a deterministic in-memory payload.

    Wikipedia OpenSearch requests get the canonical 4-element list shape the
    providers parse; every other URL gets a small HTML document.
    """
    import httpx

    url = str(request.url)
    if "wikipedia.org" in url and "action=opensearch" in url:
        return httpx.Response(
            200,
            json=[
                "Paris",
                ["Paris"],
                ["Paris est la capitale de la France."],
                ["https://fr.wikipedia.org/wiki/Paris"],
            ],
        )
    if "wikipedia.org" in url:
        return httpx.Response(
            200,
            html=(
                "<html><body><h1>Paris</h1><p>Paris est la capitale de la "
                "France et sa plus grande ville.</p></body></html>"
            ),
        )
    return httpx.Response(200, text="mocked web page")


@pytest.fixture
def mock_web(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Install a default ``httpx.MockTransport`` on every ``AsyncClient``.

    The §9/§10 connectors build their own ``httpx.AsyncClient``, so the
    transport is injected at construction time instead of being threaded
    through every provider. The returned handler can be replaced by the test
    with ``monkeypatch.setattr(httpx.AsyncClient, "__init__", ...)`` again or
    simply left as the deterministic default.
    """
    import httpx

    handler = default_web_handler
    original_init = httpx.AsyncClient.__init__

    def _init(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _init)
    return handler

