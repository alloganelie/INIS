"""Tests for the real ModelRouter.complete path (httpx MockTransport, no network)."""

import httpx
import pytest

from app.core.errors import InfrastructureError
from app.llm.router.model_router import LLMTask, ModelRouter


def _client(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


def _completion(content: str) -> dict:
    return {
        "id": "chatcmpl-mock",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 7},
    }


class TestModelRouterReal:
    """Tests covering routing and mocked real-call behaviour."""

    def test_route_uses_env_var_per_task(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A task-specific environment variable overrides the decision table."""
        monkeypatch.setenv("LLM_MODEL_UNDERSTANDING", "test-model")

        assert ModelRouter().route("understanding") == "test-model"

    def test_route_falls_back_to_env_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The global default applies when no task-specific value is set."""
        monkeypatch.delenv("LLM_MODEL_PLANNING", raising=False)
        monkeypatch.setenv("LLM_MODEL_DEFAULT", "default-model")

        assert ModelRouter().route("planning") == "default-model"

    def test_route_falls_back_to_hardcoded_table(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
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

    async def test_complete_stub_without_api_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without LLM_API_KEY, complete returns a stub and calls nothing."""
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        router = ModelRouter()
        response = await router.complete(
            LLMTask(task_type="understanding"), "Explain the request"
        )
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

    async def test_complete_http_error_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A 500 from the API surfaces as InfrastructureError."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": "boom"})

        monkeypatch.setenv("LLM_API_KEY", "test-key")
        router = ModelRouter()
        with pytest.raises(InfrastructureError, match="LLM call failed"):
            await router.complete(
                LLMTask(task_type="planning"), "Plan this", client=_client(handler)
            )
