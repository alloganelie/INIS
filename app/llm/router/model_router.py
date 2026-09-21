"""Model Router for LLM selection per INIS spec §22.

The router keeps the original selection logic (``route``) and adds the real
call contract from §22.1::

    async def complete(self, task: LLMTask, prompt: str, **kwargs) -> LLMResponse

Real calls use an OpenAI-compatible ``/chat/completions`` endpoint over
``httpx``. Without an ``LLM_API_KEY`` environment variable the router
returns a deterministic stub response and issues no network call, so every
caller works offline (tests, development, CI).
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.errors import InfrastructureError

ENV_API_KEY = "LLM_API_KEY"
ENV_BASE_URL = "LLM_BASE_URL"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass
class LLMTask:
    """Task submitted to the router (spec §22.1 ``complete`` contract)."""

    task_type: str
    cost_budget: float | None = None
    latency_budget: float | None = None
    model: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None


@dataclass
class LLMResponse:
    """Result of a routed LLM call (real or stub)."""

    content: str
    model: str
    stub: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    raw: dict[str, Any] | None = None


class ModelRouter:
    """Routes LLM requests to appropriate models based on task requirements.

    Decision criteria per §22.2:
    - task nature
    - cost budget
    - latency budget
    - context size
    - reasoning capability
    - multimodality
    - availability

    Absolute rule per §22.3: the LLM is never the single source of a fact;
    it only assists (understanding, planning, classification, comparison,
    hypotheses, contradiction detection, confidence signals).
    """

    def __init__(
        self,
        default_base_url: str | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the model router with default decision table."""
        self._decision_table = {
            "reasoning": "openai/gpt-4",
            "understanding": "openai/gpt-4",
            "classification": "openai/gpt-3.5-turbo",
            "extraction": "openai/gpt-3.5-turbo",
            "planning": "openai/gpt-4",
            "confidence_signal": "openai/gpt-3.5-turbo",
            "conflict_detection": "openai/gpt-4",
            "default": "openai/gpt-3.5-turbo",
        }
        self._default_base_url = default_base_url
        self._timeout_seconds = timeout_seconds

    def route(
        self,
        task_type: str,
        cost_budget: float | None = None,
        latency_budget: float | None = None,
    ) -> str:
        """Select appropriate model based on task requirements.

        Args:
            task_type: Type of task (e.g., "reasoning", "classification", "extraction").
            cost_budget: Maximum cost per request (optional).
            latency_budget: Maximum latency in seconds (optional).

        Returns:
            Model identifier string.

        """
        if task_type not in self._decision_table:
            task_type = "default"

        env_key = f"LLM_MODEL_{task_type.upper()}"
        if os.environ.get(env_key, "").strip():
            return os.environ[env_key].strip()

        if os.environ.get("LLM_MODEL_DEFAULT", "").strip():
            return os.environ["LLM_MODEL_DEFAULT"].strip()

        if os.environ.get("LLM_MODEL", "").strip():
            return os.environ["LLM_MODEL"].strip()

        return self._decision_table[task_type]

    def register_model(self, task_type: str, model_id: str) -> None:
        """Register a model for a specific task type.

        Args:
            task_type: Type of task.
            model_id: Model identifier.
        """
        self._decision_table[task_type] = model_id

    async def complete(self, task: LLMTask, prompt: str, **kwargs: Any) -> LLMResponse:
        """Execute a task against the routed model (spec §22.1).

        Without an ``LLM_API_KEY`` environment variable a deterministic stub
        response is returned and no network call is issued.

        Args:
            task: Task descriptor (type, budgets, optional model override).
            prompt: Prompt text to send to the model.
            **kwargs: Optional ``client`` (injected ``httpx.AsyncClient``,
                e.g. with ``MockTransport`` in tests), ``base_url``,
                ``timeout_seconds`` and ``extra_body`` merged into the
                OpenAI-compatible request payload.

        Returns:
            LLMResponse with content, model, token usage and latency.

        Raises:
            ValueError: If the prompt is empty or the task type is unknown.
            InfrastructureError: If the real API call fails.
        """
        if not prompt or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")
        model = task.model or self.route(task.task_type, task.cost_budget, task.latency_budget)

        api_key = os.environ.get(ENV_API_KEY)
        if not api_key:
            return LLMResponse(
                content=(
                    f"[stub:{model}] task '{task.task_type}' received "
                    f"({len(prompt)} chars); set {ENV_API_KEY} for a real call."
                ),
                model=model,
                stub=True,
            )

        base_url = (
            kwargs.get("base_url")
            or self._default_base_url
            or os.environ.get(ENV_BASE_URL, DEFAULT_BASE_URL)
        )
        timeout = kwargs.get("timeout_seconds", self._timeout_seconds)
        client = kwargs.get("client")
        owns_client = client is None
        if owns_client:
            client = httpx.AsyncClient(timeout=timeout)

        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if task.max_tokens is not None:
            payload["max_tokens"] = task.max_tokens
        if task.temperature is not None:
            payload["temperature"] = task.temperature
        extra_body = kwargs.get("extra_body")
        if extra_body:
            payload.update(extra_body)

        started = time.perf_counter()
        try:
            response = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise InfrastructureError(f"LLM call failed (model {model}): {exc}") from exc
        finally:
            if owns_client:
                await client.aclose()
        latency_ms = int((time.perf_counter() - started) * 1000)

        try:
            content = str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise InfrastructureError(
                f"LLM call returned an unexpected payload: {exc}"
            ) from exc
        usage = data.get("usage") or {}
        return LLMResponse(
            content=content,
            model=model,
            stub=False,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=latency_ms,
            raw=data if isinstance(data, dict) else None,
        )
