"""Tests for the LLM task wrappers (router + task_type, stub and mocked)."""

import httpx
import pytest

from app.llm.prompts import build_classification, build_understanding
from app.llm.tasks import ClassificationTask, UnderstandingTask


def _client(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


class TestTasks:
    """2 tests covering stub mode and a mocked real call."""

    async def test_understanding_run_stub_mode(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without LLM_API_KEY the task returns a stub dict."""
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        task = UnderstandingTask()
        result = await task.run(build_understanding(objective="Assess Q2 outlook"))
        assert result["task_type"] == "understanding"
        assert result["stub"] is True
        assert result["model"] == "gpt-4"
        assert result["content"]

    async def test_classification_run_mocked_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """With LLM_API_KEY and a mocked transport the content flows through."""
        monkeypatch.setenv("LLM_API_KEY", "test-key")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": '{"label": "factual"}'}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 3},
                },
            )

        task = ClassificationTask()
        result = await task.run(
            build_classification(
                content="GDP grew 1.2%",
                candidate_labels=["factual", "hypothesis"],
            ),
            client=_client(handler),
        )
        assert result["task_type"] == "classification"
        assert result["stub"] is False
        assert "factual" in result["content"]
