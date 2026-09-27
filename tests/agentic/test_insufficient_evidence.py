"""§33.3 scenario 4 — « information insuffisante ».

When no source can be found for an objective, INIS must say so: the delivery
carries §1.3 ``INSUFFICIENT_EVIDENCE``, every unsourced claim is demoted to an
``assumptions[]`` entry with ``epistemic_status=hypothesis`` / ``reason=no_source``
(§33.4, §0.2), and ``limitations[]`` states what could not be established.

Mocked providers only — no Docker, no network.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.core.statuses import INSUFFICIENT_EVIDENCE_STATUS, OUTPUT_STATUSES
from app.domain.value_objects.ulid import ULID


@pytest.fixture
def no_source(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """The web provider finds nothing for any query."""
    search = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search", search
    )
    return search


@pytest.mark.asyncio
async def test_no_source_found_yields_insufficient_evidence(
    no_source: AsyncMock, mock_llm
) -> None:
    """Zero sources → INSUFFICIENT_EVIDENCE, empty findings, explicit limits."""
    mock_llm.configure(
        json.dumps(
            {
                "summary": "Aucune source disponible.",
                "findings": [
                    "L'inflation atteindrait 3 % en 2027.",
                    "La banque centrale agirait en septembre.",
                ],
            }
        )
    )

    delivery = await PipelineRunner().run(
        ULID.new("REQ_"), {"objective": "quel sera le taux d'inflation en 2027 ?"}
    )

    assert no_source.await_count >= 1, "the plan must have looked for sources"
    assert delivery["status"] == INSUFFICIENT_EVIDENCE_STATUS
    assert delivery["status"] in OUTPUT_STATUSES

    # §0.2 — nothing unsourced may appear as a finding.
    assert delivery["findings"] == []

    # The claims are preserved, but honestly labelled as hypotheses.
    assert len(delivery["assumptions"]) >= 2
    assert all(a["epistemic_status"] == "hypothesis" for a in delivery["assumptions"])
    assert all(a["reason"] == "no_source" for a in delivery["assumptions"])

    # ... and the delivery states its limitations rather than staying silent.
    assert delivery["limitations"]
    assert any("§0.2" in limitation for limitation in delivery["limitations"])

