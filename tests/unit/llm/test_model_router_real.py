"""Tests for the real ModelRouter.complete path (httpx MockTransport, no network)."""

import json

import httpx
import pytest

from app.core.errors import InfrastructureError
from app.llm.router.model_router import LLMTask, ModelRouter


@pytest.fixture(autouse=True)
def _isolate_llm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep ambient §22.2 overrides out of the unit tests.

    A developer's ``LLM_MODEL_FALLBACKS`` or ``LLM_RETRY_ATTEMPTS`` must not
    change how many HTTP calls a unit test observes.
    """
    monkeypatch.delenv("LLM_MODEL_FALLBACKS", raising=False)
    monkeypatch.delenv("LLM_RETRY_ATTEMPTS", raising=False)


def _client(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def _completion(content: str) -> dict:
    return {
        "id": "chatcmpl-mock",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 7},
    }


def _provider_error() -> dict:
    """OpenRouter's HTTP-200 error envelope (upstream provider failure)."""
    return {
        "id": "gen-mock",
        "error": {
            "message": "Upstream error from Nvidia: Service temporarily overloaded",
            "code": 503,
            "metadata": {"error_type": "provider_overloaded"},
        },
    }


class TestModelRouterReal:
    """Tests covering routing and mocked real-call behaviour."""

    def test_route_uses_env_var_per_task(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A task-specific environment variable overrides the decision table."""
        monkeypatch.setenv("LLM_MODEL_UNDERSTANDING", "test-model")

        assert ModelRouter().route("understanding") == "test-model"

    def test_route_falls_back_to_env_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The global default applies when no task-specific value is set."""
        monkeypatch.delenv("LLM_MODEL_PLANNING", raising=False)
        monkeypatch.setenv("LLM_MODEL_DEFAULT", "default-model")

        assert ModelRouter().route("planning") == "default-model"

    def test_route_falls_back_to_hardcoded_table(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The decision table remains the final fallback."""
        monkeypatch.delenv("LLM_MODEL_UNDERSTANDING", raising=False)
        monkeypatch.delenv("LLM_MODEL_DEFAULT", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)
        router = ModelRouter()

        assert router.route("understanding") == router._decision_table["understanding"]

    def test_route_unknown_task_falls_back_to_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Unknown task types silently use the default configured model."""
        monkeypatch.delenv("LLM_MODEL_DEFAULT", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)
        router = ModelRouter()

        assert router.route("nonexistent") == router._decision_table["default"]

    async def test_complete_stub_without_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without LLM_API_KEY, complete returns a stub and calls nothing."""
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        router = ModelRouter()
        response = await router.complete(LLMTask(task_type="understanding"), "Explain the request")
        assert response.stub is True
        assert response.model == "openai/gpt-4"
        assert "understanding" in response.content

    async def test_complete_real_call_with_mock_transport(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With LLM_API_KEY, complete POSTs /chat/completions (mocked)."""
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/v1/chat/completions"
            assert request.headers["authorization"] == "Bearer test-key"
            return httpx.Response(200, json=_completion("parsed understanding"))

        router = ModelRouter()
        response = await router.complete(
            LLMTask(task_type="classification"),
            "Classify this",
            client=_client(handler),
        )
        assert response.stub is False
        assert response.content == "parsed understanding"
        assert response.model == "openai/gpt-3.5-turbo"
        assert response.input_tokens == 12
        assert response.output_tokens == 7

    async def test_complete_http_error_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A 500 from the API surfaces as InfrastructureError."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        monkeypatch.setenv("LLM_API_KEY", "test-key")
        router = ModelRouter()
        with pytest.raises(InfrastructureError, match="LLM call failed"):
            await router.complete(
                LLMTask(task_type="planning"), "Plan this", client=_client(handler)
            )

    async def test_complete_rejects_an_http_200_error_envelope(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 200 body carrying ``error`` (OpenRouter) is a real failure."""
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_provider_error())

        router = ModelRouter(retry_attempts=1)
        with pytest.raises(InfrastructureError, match="upstream error 503"):
            await router.complete(
                LLMTask(task_type="reasoning"),
                "Answer the question",
                client=_client(handler),
            )

    async def test_complete_names_the_keys_of_a_malformed_payload(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A success payload without ``choices`` reports the keys it received."""
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"id": "gen-mock"})

        router = ModelRouter(retry_attempts=1)
        with pytest.raises(InfrastructureError, match=r"keys=\['id'\]"):
            await router.complete(LLMTask(task_type="reasoning"), "Answer", client=_client(handler))

    async def test_complete_retries_an_overloaded_upstream(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """§41.8 — one transient upstream failure is retried, then succeeds."""
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(200, json=_provider_error())
            return httpx.Response(200, json=_completion("recovered answer"))

        router = ModelRouter(retry_attempts=2, retry_backoff_seconds=0.0)
        response = await router.complete(
            LLMTask(task_type="reasoning"),
            "Answer the question",
            client=_client(handler),
        )
        assert response.content == "recovered answer"
        assert response.stub is False
        assert len(calls) == 2

    async def test_complete_stops_after_the_retry_budget(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The upstream error surfaces once every attempt is exhausted."""
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(200, json=_provider_error())

        router = ModelRouter(retry_attempts=3, retry_backoff_seconds=0.0)
        with pytest.raises(InfrastructureError, match="upstream error 503"):
            await router.complete(LLMTask(task_type="reasoning"), "Answer", client=_client(handler))
        assert len(calls) == 3

    async def test_complete_retries_a_server_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """§41.8 — an HTTP 5xx is retried too, not surfaced immediately."""
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(503, json={"error": "provider down"})
            return httpx.Response(200, json=_completion("second try"))

        router = ModelRouter(retry_attempts=2, retry_backoff_seconds=0.0)
        response = await router.complete(
            LLMTask(task_type="planning"), "Plan this", client=_client(handler)
        )
        assert response.content == "second try"
        assert len(calls) == 2

    def test_retry_attempts_must_be_at_least_one(self) -> None:
        """An empty retry budget is a configuration error, not silent retrying."""
        with pytest.raises(ValueError, match="retry_attempts"):
            ModelRouter(retry_attempts=0)

    def test_retry_backoff_cannot_be_negative(self) -> None:
        """A negative backoff would sleep backwards; reject it early."""
        with pytest.raises(ValueError, match="retry_backoff_seconds"):
            ModelRouter(retry_backoff_seconds=-1.0)


def _model_of(request: httpx.Request) -> str:
    """Return the ``model`` field carried by a MockTransport request body."""
    return json.loads(request.content)["model"]


class TestRetryBudget:
    """§41.8 — the default retry budget is three tries per model."""

    def test_default_retry_budget_is_three(self) -> None:
        router = ModelRouter()
        assert router.retry_attempts == 3

    def test_llm_retry_attempts_overrides_the_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_RETRY_ATTEMPTS", "5")
        assert ModelRouter().retry_attempts == 5

    def test_a_bad_llm_retry_attempts_falls_back_to_three(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_RETRY_ATTEMPTS", "not-a-number")
        assert ModelRouter().retry_attempts == 3

    def test_explicit_constructor_budget_wins_over_the_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_RETRY_ATTEMPTS", "5")
        assert ModelRouter(retry_attempts=1).retry_attempts == 1


class TestFallbackChain:
    """§22.2 — the candidate chain and the cascade behaviour."""

    def test_model_chain_orders_primary_then_configured_fallbacks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MODEL_DEFAULT", "primary/model")
        monkeypatch.setenv("LLM_MODEL_FALLBACKS", "second/best, third/least")

        chain = ModelRouter().model_chain(LLMTask(task_type="planning"))
        assert chain == ["primary/model", "second/best", "third/least"]

    def test_model_chain_dedups_and_drops_blank_entries(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MODEL_DEFAULT", "primary/model")
        monkeypatch.setenv("LLM_MODEL_FALLBACKS", " primary/model ,, dup , dup ,")

        assert ModelRouter().model_chain(LLMTask(task_type="classification")) == [
            "primary/model",
            "dup",
        ]

    def test_zero_cost_budget_filters_billed_fallbacks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MODEL_DEFAULT", "paid/primary")
        monkeypatch.setenv("LLM_MODEL_FALLBACKS", "free/first:free, paid/second, free/third:free")

        chain = ModelRouter().model_chain(LLMTask(task_type="planning", cost_budget=0.0))
        # The primary stays (it is the caller's explicit choice), billed
        # fallbacks are never *added* on top of a zero-cost budget.
        assert chain == ["paid/primary", "free/first:free", "free/third:free"]

    def test_constructor_chain_wins_over_the_environment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("LLM_MODEL_FALLBACKS", "env/only:free")
        router = ModelRouter(fallback_models=["explicit/free:free"])

        assert router.configured_fallbacks() == ["explicit/free:free"]

    async def test_complete_served_by_the_next_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """§22.2 — a primary drowned under a 503 is retried, then replaced."""
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("LLM_MODEL_DEFAULT", "primary/overloaded")
        monkeypatch.setenv("LLM_MODEL_FALLBACKS", "backup/free")
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            model = _model_of(request)
            calls.append(model)
            if model == "primary/overloaded":
                return httpx.Response(200, json=_provider_error())
            return httpx.Response(200, json=_completion("served by backup"))

        router = ModelRouter(retry_attempts=2, retry_backoff_seconds=0.0)
        response = await router.complete(
            LLMTask(task_type="planning"), "Plan it", client=_client(handler)
        )
        assert response.stub is False
        assert response.content == "served by backup"
        assert response.model == "backup/free"
        # §41.8 retries exhausted on the primary (two tries) *before* the walk.
        assert calls == ["primary/overloaded", "primary/overloaded", "backup/free"]

    async def test_complete_aggregates_every_cause_when_all_fallbacks_fail(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """§22.2 — the final error keeps the cause of each candidate."""
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("LLM_MODEL_DEFAULT", "first/fails")
        monkeypatch.setenv("LLM_MODEL_FALLBACKS", "second/fails")
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(_model_of(request))
            return httpx.Response(200, json=_provider_error())

        router = ModelRouter(retry_attempts=1, retry_backoff_seconds=0.0)
        with pytest.raises(
            InfrastructureError,
            match=r"all LLM models failed.*first/fails.*second/fails.*upstream error 503",
        ):
            await router.complete(LLMTask(task_type="reasoning"), "Why", client=_client(handler))
        assert calls == ["first/fails", "second/fails"]

    async def test_latency_budget_stops_the_fallback_walk(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """§22.2 — ``latency_budget`` bounds the cascade, not just one call."""
        monkeypatch.setenv("LLM_API_KEY", "test-key")
        monkeypatch.setenv("LLM_MODEL_DEFAULT", "slow/primary")
        monkeypatch.setenv("LLM_MODEL_FALLBACKS", "even/slower")
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(_model_of(request))
            return httpx.Response(200, json=_provider_error())

        router = ModelRouter(retry_attempts=1, retry_backoff_seconds=0.0)
        with pytest.raises(InfrastructureError, match=r"latency budget"):
            await router.complete(
                LLMTask(task_type="planning", latency_budget=0.0),
                "Hurry",
                client=_client(handler),
            )
        # The primary is always attempted; the second candidate is not.
        assert calls == ["slow/primary"]


class TestHelpers:
    """Module-level helpers used by the chain parsing."""

    def test_parse_model_chain(self) -> None:
        from app.llm.router.model_router import parse_model_chain

        assert parse_model_chain(" a, b ,,b, c ") == ["a", "b", "c"]
        assert parse_model_chain("") == []
        assert parse_model_chain(None) == []

    def test_is_free_model(self) -> None:
        from app.llm.router.model_router import is_free_model

        assert is_free_model("vendor/model:free") is True
        assert is_free_model("vendor/model") is False
        assert is_free_model("") is False
