"""CI guards for §41.2 metering and §41.12 tracing of the LLM synthesis.

Backstory: an out-of-repo E2E harness used to green-light requests whose LLM
synthesis had actually failed (upstream ``:free`` provider overload). These
tests encode the same invariants in CI, fully offline:

- a *served* synthesis is visible in the usage report *and* carries its real
  token counts in the §41.12 decision trace;
- a *failed* or *stubbed* synthesis is stated (zero tokens, cause in the trace)
  and is never mistakable for a served call.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.core.errors import InfrastructureError
from app.domain.value_objects.ulid import ULID
from app.llm.router.model_router import LLMResponse, LLMTask

#: The synthesis prompt is the only router call carrying this marker, so a test
#: double can fail *only* the synthesis phase (spéc §22.1).
_SYNTHESIS_MARKER = "Réponds en français"
_SERVED_SUMMARY = "Synthèse pilotée par le LLM."


def _synthesis_traces(runner: PipelineRunner, request_id: str) -> list[dict[str, Any]]:
    """Return the §41.12 traces the runner recorded for the synthesis phase."""
    return [
        trace
        for trace in runner.llm_traces(request_id)
        if str(trace.get("decision_summary", "")).startswith("[synthesis]")
    ]


async def _run(objective: str) -> tuple[PipelineRunner, dict[str, Any]]:
    """Run the pipeline on a fresh runner and return ``(runner, delivery)``."""
    runner = PipelineRunner()
    request_id = ULID.new("REQ_")
    delivery = await runner.run(
        request_id,
        {"objective": objective, "request_type": "research"},
    )
    return runner, delivery


@pytest.mark.asyncio
async def test_a_served_synthesis_is_metered_and_traced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A served synthesis must be visible in usage *and* traces (§41.2)."""

    async def mock_complete(self: Any, task: LLMTask, prompt: str, **kwargs: Any) -> LLMResponse:
        if _SYNTHESIS_MARKER not in prompt:
            return LLMResponse(content="[stub:test]", model="test-model", stub=True)
        return LLMResponse(
            content=json.dumps({"summary": _SERVED_SUMMARY, "findings": []}),
            model="test-model",
            stub=False,
            input_tokens=111,
            output_tokens=42,
        )

    monkeypatch.setattr("app.llm.router.model_router.ModelRouter.complete", mock_complete)

    runner, delivery = await _run("synthesis metering probe")

    traces = _synthesis_traces(runner, delivery["request_id"])
    assert len(traces) == 1
    assert traces[0]["input_token_count"] == 111
    assert traces[0]["output_token_count"] == 42
    assert "failed" not in traces[0]["decision_summary"]
    usage = delivery["usage_report"]
    assert usage["tokens_llm_input"] >= 111
    assert usage["tokens_llm_output"] >= 42
    assert delivery["summary"] == _SERVED_SUMMARY


@pytest.mark.asyncio
async def test_a_failed_synthesis_never_passes_for_served(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A crashed call is brought down with zero tokens and the cause, never
    presented as a served synthesis (§25)."""
    objective = "synthesis failure probe"

    async def mock_complete(self: Any, task: LLMTask, prompt: str, **kwargs: Any) -> LLMResponse:
        if _SYNTHESIS_MARKER not in prompt:
            return LLMResponse(content="[stub:test]", model="test-model", stub=True)
        raise InfrastructureError("LLM call failed (model free/primary:free): upstream error 503")

    monkeypatch.setattr("app.llm.router.model_router.ModelRouter.complete", mock_complete)

    runner, delivery = await _run(objective)

    traces = _synthesis_traces(runner, delivery["request_id"])
    assert len(traces) == 1
    assert traces[0]["input_token_count"] == 0
    assert traces[0]["output_token_count"] == 0
    assert "failed" in traces[0]["decision_summary"]
    # The trace names the model that was attempted, so an operator knows what
    # to look at first.
    assert traces[0]["model_used"]
    usage = delivery["usage_report"]
    assert usage["tokens_llm_input"] == 0
    assert usage["tokens_llm_output"] == 0
    # The delivery honestly falls back to the deterministic summary instead of
    # surfacing a fabricated synthesis text.
    assert delivery["summary"] == f"Synthesized research report for '{objective}'."
    # No unsourced claim has been promoted to a finding (§0.2 invariant 8).
    for finding in delivery.get("information_units") or []:
        source_id = finding.get("source_id") or (finding.get("evidence") or {}).get("source_id")
        assert source_id, f"unsourced finding promoted: {finding!r}"


@pytest.mark.asyncio
async def test_a_stubbed_synthesis_is_stated_not_hidden(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stubbed call is traced with zero tokens, not counted as a success."""

    async def mock_complete(self: Any, task: LLMTask, prompt: str, **kwargs: Any) -> LLMResponse:
        return LLMResponse(content="[stub:test]", model="test-model", stub=True)

    monkeypatch.setattr("app.llm.router.model_router.ModelRouter.complete", mock_complete)

    runner, delivery = await _run("stub synthesis probe")

    traces = _synthesis_traces(runner, delivery["request_id"])
    assert len(traces) == 1
    assert traces[0]["input_token_count"] == 0
    assert "stubbed" in traces[0]["decision_summary"]
    usage = delivery["usage_report"]
    assert usage["tokens_llm_input"] == 0
    assert usage["tokens_llm_output"] == 0
