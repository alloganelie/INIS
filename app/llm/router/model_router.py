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

import asyncio
import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.errors import InfrastructureError
from app.core.logging import get_logger

ENV_API_KEY = "LLM_API_KEY"
ENV_BASE_URL = "LLM_BASE_URL"
#: §22.2 ordered fallback chain, comma separated, most preferred first.
ENV_FALLBACK_MODELS = "LLM_MODEL_FALLBACKS"
#: §41.8 total tries per model, overriding ``DEFAULT_RETRY_ATTEMPTS``.
ENV_RETRY_ATTEMPTS = "LLM_RETRY_ATTEMPTS"
DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0

#: Total tries per model, including the first one (§41.8 retry policy).
#: Three tries absorb the transient ``:free`` gateway overloads without
#: stretching a single request into an unbounded wait.
DEFAULT_RETRY_ATTEMPTS = 3
#: Base delay between two attempts (linear backoff: ``base * attempt``).
DEFAULT_RETRY_BACKOFF_SECONDS = 0.5
#: Gateway tag marking a model the provider does not bill (OpenRouter ``:free``).
FREE_MODEL_TAG = ":free"

#: Delivery logger — a failed model is stated before the chain moves on (§22.2).
logger = get_logger(__name__)


def upstream_error(data: Any) -> str | None:
    """Return the provider error carried by an HTTP 200 body, if any.

    Some gateways (OpenRouter among them) answer ``200 OK`` with
    ``{"id": ..., "error": {"code": 503, "message": ...}}`` when the upstream
    provider is overloaded. Ignoring that envelope makes a failed call look
    like a success and the caller then crashes on the missing ``choices`` key,
    losing the real cause (§22.1).
    """
    if not isinstance(data, dict):
        return None
    error = data.get("error")
    if isinstance(error, dict):
        code = error.get("code") or error.get("status") or "unknown"
        return f"upstream error {code}: {error.get('message') or error}"
    if isinstance(error, str) and error.strip():
        return f"upstream error: {error.strip()}"
    return None


def parse_model_chain(value: str | None) -> list[str]:
    """Split a comma-separated model list into an ordered, deduplicated chain.

    Blank entries and stray separators (``"a,,b,"``) are dropped, so a sloppy
    ``LLM_MODEL_FALLBACKS`` value degrades to a shorter chain instead of sending
    an empty model identifier to the provider (§22.2).
    """
    chain: list[str] = []
    for candidate in (value or "").split(","):
        model = candidate.strip()
        if model and model not in chain:
            chain.append(model)
    return chain


def is_free_model(model_id: str) -> bool:
    """Return True when the gateway prices the model as free (§22.2 budget)."""
    return bool(model_id) and model_id.strip().endswith(FREE_MODEL_TAG)


def _env_positive_int(name: str) -> int | None:
    """Read a strictly positive integer env var, or ``None`` when unusable.

    An unset, empty, non-numeric or non-positive value is reported and ignored:
    a typo must never shrink the retry budget to zero and silently disable
    retrying (§41.8).
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        logger.warning("Ignoring a non-numeric environment variable", name=name, value=raw)
        return None
    if value < 1:
        logger.warning("Ignoring a non-positive environment variable", name=name, value=raw)
        return None
    return value


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
        retry_attempts: int | None = None,
        retry_backoff_seconds: float = DEFAULT_RETRY_BACKOFF_SECONDS,
        fallback_models: list[str] | None = None,
    ) -> None:
        """Initialize the model router with default decision table.

        Args:
            default_base_url: OpenAI-compatible base URL override.
            timeout_seconds: Per-call HTTP timeout.
            retry_attempts: Total tries per model, including the first (§41.8).
                ``None`` reads ``LLM_RETRY_ATTEMPTS`` on every call and falls
                back to ``DEFAULT_RETRY_ATTEMPTS``.
            retry_backoff_seconds: Base delay before a retry (linear backoff).
            fallback_models: Ordered §22.2 fallback chain, most preferred first.
                ``None`` reads ``LLM_MODEL_FALLBACKS`` on every call.

        Raises:
            ValueError: If ``retry_attempts`` is below 1 or the backoff negative.
        """
        if retry_attempts is not None and retry_attempts < 1:
            raise ValueError("retry_attempts must be >= 1")
        if retry_backoff_seconds < 0:
            raise ValueError("retry_backoff_seconds must be >= 0")
        self._retry_attempts = retry_attempts
        self._retry_backoff_seconds = retry_backoff_seconds
        self._fallback_models = list(fallback_models) if fallback_models is not None else None
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

    @property
    def retry_attempts(self) -> int:
        """Return the effective §41.8 retry budget, including the first try."""
        if self._retry_attempts is not None:
            return self._retry_attempts
        return _env_positive_int(ENV_RETRY_ATTEMPTS) or DEFAULT_RETRY_ATTEMPTS

    @property
    def retry_backoff_seconds(self) -> float:
        """Return the base backoff delay between two attempts."""
        return self._retry_backoff_seconds

    def configured_fallbacks(self) -> list[str]:
        """Return the configured §22.2 fallback chain, most preferred first.

        A chain passed to the constructor wins over ``LLM_MODEL_FALLBACKS`` so
        an explicit deployment decision is never overridden by the ambient
        environment.
        """
        if self._fallback_models is not None:
            return list(self._fallback_models)
        return parse_model_chain(os.environ.get(ENV_FALLBACK_MODELS))

    def model_chain(self, task: LLMTask) -> list[str]:
        """Return every candidate model for *task*, most preferred first (§22.2).

        The chain is the primary model — ``task.model`` when given, otherwise the
        model ``route`` selects — followed by the configured fallbacks in
        configuration order. Duplicates are dropped so a model listed twice is
        never called twice for the same task.

        A ``cost_budget`` of zero or less restricts the *fallbacks* to models the
        gateway does not bill (``:free`` suffix): a zero budget cannot pay for a
        billed model. The primary stays first even then, because it is the
        caller's explicit choice, but a billed model is never added on top of it.

        Args:
            task: Task descriptor carrying the optional model and budgets.

        Returns:
            Non-empty ordered list of model identifiers.
        """
        primary = task.model or self.route(task.task_type, task.cost_budget, task.latency_budget)
        fallbacks = self.configured_fallbacks()
        if task.cost_budget is not None and task.cost_budget <= 0:
            fallbacks = [model for model in fallbacks if is_free_model(model)]
        chain: list[str] = []
        for candidate in [primary, *fallbacks]:
            model = candidate.strip() if isinstance(candidate, str) else ""
            if model and model not in chain:
                chain.append(model)
        return chain

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

        The model actually called is the first candidate of
        :meth:`model_chain`: ``task.model`` when given, otherwise the routed
        model. Each candidate is retried per §41.8, then the next one is tried,
        so an overloaded free provider no longer fails the request outright.
        ``LLMResponse.model`` always names the model that answered.

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
            InfrastructureError: If every candidate model failed, carrying the
                cause of each one.
        """
        if not prompt or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")

        chain = self.model_chain(task)
        api_key = os.environ.get(ENV_API_KEY)
        if not api_key:
            return LLMResponse(
                content=(
                    f"[stub:{chain[0]}] task '{task.task_type}' received "
                    f"({len(prompt)} chars); set {ENV_API_KEY} for a real call."
                ),
                model=chain[0],
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

        failures: list[str] = []
        chain_started = time.perf_counter()
        try:
            for index, model in enumerate(chain):
                if index and self._latency_budget_spent(task, chain_started):
                    # §22.2 — a bounded chain: the caller asked for an answer
                    # within ``latency_budget``, so walking six providers is not
                    # an option. The refusal states how far the chain went.
                    failures.append(
                        f"latency budget of {task.latency_budget}s exhausted before trying {model}"
                    )
                    break
                try:
                    response = await self._call_model(
                        model,
                        base_url=base_url,
                        api_key=api_key,
                        task=task,
                        prompt=prompt,
                        client=client,
                        extra_body=kwargs.get("extra_body"),
                    )
                except InfrastructureError as exc:
                    # §22.2 — a failed model is not a failed request: state the
                    # cause, then walk down the configured chain.
                    failures.append(str(exc))
                    remaining = chain[index + 1 :]
                    if remaining:
                        logger.warning(
                            "LLM model failed; trying the next fallback",
                            model=model,
                            error=str(exc),
                            fallbacks_remaining=len(remaining),
                            next_model=remaining[0],
                        )
                    continue
                if index:
                    logger.warning(
                        "LLM call served by a fallback model",
                        model=model,
                        primary=chain[0],
                        fallback_rank=index,
                    )
                return response
        finally:
            if owns_client:
                await client.aclose()
        raise InfrastructureError("all LLM models failed (§22.2): " + " | ".join(failures))

    def _latency_budget_spent(self, task: LLMTask, chain_started: float) -> bool:
        """Return True when the §22.2 latency budget is already consumed.

        The primary model is always attempted, so a budget too small to fit even
        one call degrades to "one call, no fallbacks" instead of "no call at
        all": the caller still gets an answer or a precise failure.

        Args:
            task: Task descriptor carrying the optional ``latency_budget``.
            chain_started: ``time.perf_counter()`` taken before the first call.

        Returns:
            True when the remaining time cannot host another attempt.
        """
        budget = task.latency_budget
        if budget is None:
            return False
        return (time.perf_counter() - chain_started) >= budget

    async def _call_model(
        self,
        model: str,
        *,
        base_url: str,
        api_key: str,
        task: LLMTask,
        prompt: str,
        client: httpx.AsyncClient,
        extra_body: dict[str, Any] | None,
    ) -> LLMResponse:
        """Call one model with the §41.8 retry policy.

        Args:
            model: Model identifier to call.
            base_url: OpenAI-compatible base URL.
            api_key: Provider credential.
            task: Task descriptor (max tokens, temperature).
            prompt: Prompt text.
            client: HTTP client owned by the caller.
            extra_body: Extra payload keys merged into the request.

        Returns:
            LLMResponse carrying the model that actually answered.

        Raises:
            InfrastructureError: Once every attempt failed, or when the provider
                answers a payload without ``choices``.
        """
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if task.max_tokens is not None:
            payload["max_tokens"] = task.max_tokens
        if task.temperature is not None:
            payload["temperature"] = task.temperature
        if extra_body:
            payload.update(extra_body)

        attempts = self.retry_attempts
        data: Any = None
        failure: str | None = None
        started = time.perf_counter()
        for attempt in range(1, attempts + 1):
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
            except Exception as exc:  # noqa: BLE001 - transport and JSON errors
                failure = f"LLM call failed (model {model}): {exc}"
            else:
                failure = upstream_error(data)
                if failure is None:
                    break
                failure = f"LLM call failed (model {model}): {failure}"
            if attempt < attempts and self.retry_backoff_seconds:
                await asyncio.sleep(self.retry_backoff_seconds * attempt)
        if failure is not None:
            raise InfrastructureError(failure)
        latency_ms = int((time.perf_counter() - started) * 1000)

        try:
            content = str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            keys = sorted(data) if isinstance(data, dict) else type(data).__name__
            raise InfrastructureError(
                f"LLM call returned an unexpected payload (model {model}): {exc}; keys={keys}"
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
