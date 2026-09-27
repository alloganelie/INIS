"""§33.3 scenario 8 — « demande ambiguë ».

An underspecified objective must not be answered as if it were precise: the
§8 understanding stage flags the ambiguity, the delivery carries §1.3
``INSUFFICIENT_EVIDENCE`` (no evidence can support an unspecified question)
and ``missing_information[]`` lists exactly what the requester must supply,
mirrored in ``limitations[]``.

Mocked providers only — no Docker, no network.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.agents.understanding.clarification_detector import ClarificationDetector
from app.agents.understanding.request_parser import InformationRequest, RequestParser
from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.core.statuses import (
    INSUFFICIENT_EVIDENCE_STATUS,
    OUTPUT_STATUSES,
    PARTIAL_SUCCESS_STATUS,
    resolve_delivery_status,
)
from app.domain.value_objects.ulid import ULID

AMBIGUOUS_OBJECTIVE = "whatever is appropriate for the topic"


def _parse(objective: str) -> InformationRequest:
    return RequestParser().parse(objective)


def test_ambiguity_is_detected_with_reasons() -> None:
    """A vague objective yields explicit clarification reasons (§8)."""
    result = ClarificationDetector().detect(_parse(AMBIGUOUS_OBJECTIVE))

    assert result.required is True
    assert result.reasons
    assert any("ambiguous" in reason for reason in result.reasons)


def test_a_precise_objective_needs_no_clarification() -> None:
    """Control: a precise question is not flagged."""
    result = ClarificationDetector().detect(
        _parse("Quel est le taux d'inflation annuel en France ?")
    )

    assert result.required is False
    assert result.reasons == ()


def test_ambiguous_outcomes_are_only_insufficient_or_partial() -> None:
    """§1.3: an ambiguous request never reports plain success."""
    insufficient = resolve_delivery_status(findings=[])
    partial = resolve_delivery_status(findings=[{"finding": "x"}], partial=True)

    assert insufficient == INSUFFICIENT_EVIDENCE_STATUS
    assert partial == PARTIAL_SUCCESS_STATUS
    assert insufficient in OUTPUT_STATUSES
    assert partial in OUTPUT_STATUSES
    assert "completed" not in {insufficient, partial}


@pytest.mark.asyncio
async def test_pipeline_lists_the_missing_information(
    monkeypatch: pytest.MonkeyPatch, mock_llm
) -> None:
    """The delivery exposes ``missing_information[]`` for an ambiguous request."""
    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search",
        AsyncMock(return_value=[]),
    )
    mock_llm.configure('{"summary": "Rien de vérifiable.", "findings": []}')

    delivery = await PipelineRunner().run(
        ULID.new("REQ_"), {"objective": AMBIGUOUS_OBJECTIVE}
    )

    assert delivery["status"] == INSUFFICIENT_EVIDENCE_STATUS
    assert delivery["missing_information"], (
        "an ambiguous request must list what is missing instead of guessing"
    )
    assert any(
        "ambiguous" in entry for entry in delivery["missing_information"]
    )
    assert any("ambigu" in limitation.lower() for limitation in delivery["limitations"])

