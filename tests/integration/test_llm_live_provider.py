"""Opt-in live checks of the §22.2 LLM path.

Skipped by default: these tests perform real network calls against
``LLM_BASE_URL``. Opt in with::

    set INIS_LIVE_LLM=1
    set LLM_API_KEY=...
    python -m pytest -q tests/integration/test_llm_live_provider.py

They are the in-repo, CI-visible companions of the §41.2/§41.12 harness guard:
a real provider call must be served (never a stub) and metered, and the §22.2
cascade must survive a dead primary by serving the next configured candidate.
"""

from __future__ import annotations

import os

import pytest

from app.llm.router.model_router import LLMTask, ModelRouter


def _live_llm_enabled() -> bool:
    """Live checks need both an explicit opt-in and a real credential."""
    return os.environ.get("INIS_LIVE_LLM", "").strip() in {"1", "true", "yes"} and bool(
        os.environ.get("LLM_API_KEY", "").strip()
    )


pytestmark = pytest.mark.skipif(
    not _live_llm_enabled(),
    reason="live LLM checks are opt-in: INIS_LIVE_LLM=1 + LLM_API_KEY required",
)


@pytest.mark.asyncio
async def test_live_call_is_served_and_metered() -> None:
    """A real provider call returns real content and token usage (§22.1)."""
    router = ModelRouter(retry_attempts=1, retry_backoff_seconds=0.0)
    task = LLMTask(task_type="understanding", max_tokens=16)
    response = await router.complete(task, "Réponds par le seul mot : ok.")
    assert response.stub is False
    assert response.model in router.model_chain(task)
    assert response.input_tokens > 0
    assert response.output_tokens > 0
    assert response.latency_ms >= 0


@pytest.mark.asyncio
async def test_live_cascade_serves_through_the_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§22.2 — a rejected primary is replaced by the next candidate."""
    real_default = os.environ.get("LLM_MODEL_DEFAULT", "").strip()
    if not real_default:
        pytest.skip("LLM_MODEL_DEFAULT unset: cannot exercise the cascade")
    monkeypatch.setenv("LLM_MODEL_DEFAULT", "core/does-not-exist:free")
    monkeypatch.setenv("LLM_MODEL_FALLBACKS", real_default)

    router = ModelRouter(retry_attempts=1, retry_backoff_seconds=0.0)
    response = await router.complete(LLMTask(task_type="understanding", max_tokens=16), "Dis ok.")
    assert response.stub is False
    assert response.model == real_default
