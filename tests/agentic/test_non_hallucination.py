"""§33.4 — Non-hallucination.

Every factual claim delivered by INIS must be traceable to a source, an
information unit or an explicit transformation (§33.4, §0.2 invariant 8).
Claims the pipeline cannot trace are demoted to ``assumptions`` labelled
``hypothesis`` — never laundered into ``findings`` — and the §0.2 rule itself
is stated in the delivery limitations.

Mocked providers and LLM only — no Docker, no network.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.api.v1.requests.pipeline_runner import PipelineRunner
from app.domain.entities.search_result import SearchResult
from app.domain.value_objects.ulid import ULID

OBJECTIVE = "Quelle est la capitale de la France ?"
WIKI_URL = "https://fr.wikipedia.org/wiki/Paris"

#: The LLM tries to deliver one traceable fact plus four untraceable claims.
LLM_CLAIMS = {
    "summary": "Synthèse dont seul le fait sourcé est un fait.",
    "findings": [
        {
            "finding": "Paris est la capitale de la France.",
            "source_id": "SRC_WIKIPEDIA_01",
            "evidence_id": "EVID_01",
        },
        # Sourced but no evidence attached → not verifiable (§0.2).
        {"finding": "Fait sourcé sans preuve jointe.", "source_id": "SRC_WIKIPEDIA_01"},
        # The LLM itself is never a source (§0.2).
        {"finding": "Le LLM affirme X.", "source_id": "llm"},
        {"finding": "Déduction sans source.", "source_id": "hypothesis"},
        "Phrase sans aucune source.",
    ],
}


@pytest.fixture
def web_doubles(monkeypatch: pytest.MonkeyPatch) -> dict[str, AsyncMock]:
    """Mock the §9/§10 providers and extractor used by the acquisition stage."""
    result = SearchResult(
        title="Paris — Wikipédia",
        url=WIKI_URL,
        snippet="Paris est la capitale de la France.",
        score=0.95,
        provider="wikipedia",
    )
    search = AsyncMock(return_value=[result])
    extract = AsyncMock(
        return_value={
            "title": "Paris",
            "text": "Paris est la capitale de la France.",
            "language": "fr",
            "url": WIKI_URL,
            "error": None,
        }
    )
    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search", search
    )
    monkeypatch.setattr(
        "app.connectors.web.extractors.wikipedia_extractor.WikipediaExtractor.extract",
        extract,
    )
    return {"search": search, "extract": extract}


async def _run_with_llm_claims(
    mock_llm: Any, web_doubles: dict[str, AsyncMock]
) -> dict[str, Any]:
    mock_llm.configure(json.dumps(LLM_CLAIMS))
    runner = PipelineRunner()
    return await runner.run(ULID.new("REQ_"), {"objective": OBJECTIVE})


@pytest.mark.asyncio
async def test_only_traceable_claims_survive_as_findings(
    mock_llm: Any, web_doubles: dict[str, AsyncMock]
) -> None:
    """A claim without ``SRC_`` source **and** evidence never reaches ``findings``."""
    out = await _run_with_llm_claims(mock_llm, web_doubles)

    assert len(out["findings"]) == 1
    only = out["findings"][0]
    assert only["finding"] == "Paris est la capitale de la France."
    assert only["source_id"] == "SRC_WIKIPEDIA_01"
    assert only["evidence_id"] == "EVID_01"
    assert out["status"] == "completed"


@pytest.mark.asyncio
async def test_every_delivered_finding_is_traceable_to_a_source(
    mock_llm: Any, web_doubles: dict[str, AsyncMock]
) -> None:
    """§33.4 invariant: no delivered factual claim lacks a traceable provenance."""
    out = await _run_with_llm_claims(mock_llm, web_doubles)

    for finding in out["findings"]:
        assert str(finding.get("source_id", "")).startswith("SRC_"), finding
        assert finding.get("evidence_id"), finding
    # The rule itself is disclosed with the delivery, not buried.
    assert any("hypothèses §0.2" in limitation for limitation in out["limitations"])


@pytest.mark.asyncio
async def test_untraceable_claims_are_labelled_hypotheses_never_facts(
    mock_llm: Any, web_doubles: dict[str, AsyncMock]
) -> None:
    """Every dropped claim lands in ``assumptions`` with an explicit hypothesis label."""
    out = await _run_with_llm_claims(mock_llm, web_doubles)

    assert len(out["assumptions"]) == len(LLM_CLAIMS["findings"]) - 1
    for assumption in out["assumptions"]:
        assert assumption["epistemic_status"] == "hypothesis"
        assert assumption["reason"] == "no_source"

    # No laundering: a hypothesis statement never also appears as a finding.
    finding_texts = {json.dumps(f, sort_keys=True) for f in out["findings"]}
    for assumption in out["assumptions"]:
        assert not any(
            assumption["statement"] in dumped for dumped in finding_texts
        ), f"hypothesis laundered into findings: {assumption['statement']!r}"


@pytest.mark.asyncio
async def test_extractor_facts_trace_back_to_a_real_source(
    web_doubles: dict[str, AsyncMock],
) -> None:
    """Control without the LLM: real extracted facts carry the full provenance chain."""
    runner = PipelineRunner()

    out = await runner.run(ULID.new("REQ_"), {"objective": OBJECTIVE})

    assert out["findings"], "extractor facts must reach the delivery"
    source_ids = {source["source_id"] for source in out["sources"]}
    for finding in out["findings"]:
        assert finding["source_id"].startswith("SRC_")
        assert finding["source_id"] in source_ids, "every finding traces to a delivered source"
        assert finding["evidence_id"].startswith("EVID_")
        assert finding["raw_reference"]["url"] == WIKI_URL
        assert finding["provenance"]["extracted_from"] == WIKI_URL
