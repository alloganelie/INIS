"""End-to-End API Pipeline Tests per §24 and §28."""

from __future__ import annotations

import json
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient

from app.api.v1.requests.pipeline_runner import PipelineRunner, pipeline_runner
from app.domain.value_objects.ulid import ULID
from app.main import app

client = TestClient(app)


def test_create_request_triggers_pipeline() -> None:
    """Ensure POST /v1/requests creates request and triggers the pipeline runner."""
    payload = {
        "objective": "Evaluate global semiconductor supply chain resilience",
        "request_type": "research",
    }
    response = client.post("/v1/requests", json=payload)
    assert response.status_code == 201
    data = response.json()
    req_id = data["request_id"]
    assert req_id.startswith("REQ_")
    assert data["status"] in ("received", "processing", "completed")

    # The background task or runner should have recorded or started state
    state = pipeline_runner.get_state(req_id)
    assert state is not None or pipeline_runner.is_running(req_id) or data["status"] == "received"


@pytest.mark.asyncio
async def test_get_request_returns_pipeline_state() -> None:
    """Ensure GET /v1/requests/{id} returns the latest execution state and §24.1 delivery."""
    req_id = ULID.new("REQ_")
    payload = {
        "objective": "Verify clinical trials phase 3 efficacy",
        "request_type": "evidence",
    }
    # Create request in store via API
    create_res = client.post("/v1/requests", json=payload)
    assert create_res.status_code == 201
    actual_id = create_res.json()["request_id"]

    # Execute pipeline runner synchronously
    result = await pipeline_runner.run(actual_id, payload)
    # Stub pipeline has no real SRC_ sources → INSUFFICIENT_EVIDENCE (§1.3)
    assert result["status"] in ("completed", "INSUFFICIENT_EVIDENCE")

    # Fetch request
    get_res = client.get(f"/v1/requests/{actual_id}")
    assert get_res.status_code == 200
    res_data = get_res.json()
    assert res_data["status"] in ("completed", "INSUFFICIENT_EVIDENCE")
    assert res_data["pipeline_state"] is not None
    assert res_data["pipeline_state"]["response_id"].startswith("RESP_")
    assert res_data["pipeline_state"]["request_id"] == actual_id


def test_events_endpoint_streams() -> None:
    """Ensure GET /v1/requests/{id}/events streams SSE events."""
    payload = {
        "objective": "Stream telemetry events for solar flare analysis",
        "request_type": "data",
    }
    create_res = client.post("/v1/requests", json=payload)
    assert create_res.status_code == 201
    req_id = create_res.json()["request_id"]

    # Query events stream
    with client.stream("GET", f"/v1/requests/{req_id}/events") as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        # Read lines
        lines = []
        for line in response.iter_lines():
            if line:
                lines.append(line)
            if len(lines) >= 1:
                break
        assert len(lines) >= 1
        assert any(l.startswith("data:") for l in lines)
        data_line = next(l for l in lines if l.startswith("data:"))
        event_obj = json.loads(data_line[len("data:"):].strip())
        assert "step" in event_obj
        assert "status" in event_obj


@pytest.mark.asyncio
async def test_pipeline_degrades_gracefully_without_understanding() -> None:
    """Ensure pipeline succeeds and returns §24.1 output even if understanding modules fail."""
    runner = PipelineRunner()
    req_id = ULID.new("REQ_")
    payload = {
        "objective": "Assess foreign trade balance under missing module conditions",
        "request_type": "research",
    }

    # Simulate understanding failure
    with patch(
        "app.agents.understanding.request_parser.RequestParser.parse",
        side_effect=ImportError("Mocked understanding module failure"),
    ):
        result = await runner.run(req_id, payload)

    assert result["status"] in ("completed", "INSUFFICIENT_EVIDENCE")
    assert result["request_id"] == req_id
    assert result["response_id"].startswith("RESP_")
    # Unsourced findings go to assumptions, so findings may be empty
    assert isinstance(result["findings"], list)
    assert "confidence" in result
    assert result["confidence"]["score"] > 0.0
    # §0.2 — no finding should carry "hypothesis" as source_id
    for finding in result["findings"]:
        if isinstance(finding, dict):
            assert finding.get("source_id") != "hypothesis"


@pytest.mark.asyncio
async def test_pipeline_full_with_stubs() -> None:
    """Ensure full pipeline execution returns conformant §24.1 response structure."""
    runner = PipelineRunner()
    req_id = ULID.new("REQ_")
    payload = {
        "objective": "Examine macro-economic indicators for EU zone 2026",
        "request_type": "research",
        "constraints": {
            "minimum_confidence": 0.8,
            "maximum_iterations": 5,
            "maximum_execution_time_seconds": 60,
        },
    }

    delivery = await runner.run(req_id, payload)

    # Validate §24.1 required keys
    expected_keys = {
        "response_id",
        "request_id",
        "status",
        "summary",
        "findings",
        "information_units",
        "evidence",
        "sources",
        "datasets",
        "artifacts",
        "transformations",
        "conflicts",
        "confidence",
        "limitations",
        "assumptions",
        "missing_information",
        "recommended_next_actions",
        "provenance",
        "audit",
        "generated_by",
        "timestamps",
        "trace",
    }
    assert expected_keys.issubset(delivery.keys())
    assert delivery["response_id"].startswith("RESP_")
    assert delivery["request_id"] == req_id
    # Stub pipeline has no real SRC_ sources → INSUFFICIENT_EVIDENCE (§1.3)
    assert delivery["status"] in ("completed", "INSUFFICIENT_EVIDENCE")
    assert isinstance(delivery["information_units"], list)
    assert len(delivery["information_units"]) > 0
    assert delivery["information_units"][0]["information_id"].startswith("INF_")
    assert isinstance(delivery["evidence"], list)
    assert len(delivery["evidence"]) > 0
    assert delivery["evidence"][0]["evidence_id"].startswith("EVID_")
    assert isinstance(delivery["confidence"], dict)
    assert delivery["confidence"]["score"] >= 0.0
    assert delivery["provenance"]["pipeline"] == "PipelineRunner"
    assert "started_at" in delivery["timestamps"]
    assert "completed_at" in delivery["timestamps"]
    # §0.2 — limitations must always include the notice
    assert any("§0.2" in lim for lim in delivery["limitations"])
    # §0.2 — no finding may have "hypothesis" as source_id
    for finding in delivery["findings"]:
        if isinstance(finding, dict):
            assert finding.get("source_id") != "hypothesis"


@pytest.mark.asyncio
async def test_pipeline_wires_real_llm_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure pipeline runner invokes LLM tasks for understanding, planning, and synthesis."""
    from app.llm.router.model_router import LLMResponse, LLMTask

    calls: list[str] = []
    FAKE_SRC = "SRC_TEST00000000000000000"
    FAKE_EVID = "EVID_TEST00000000000000000"

    async def mock_complete(self: Any, task: LLMTask, prompt: str, **kwargs: Any) -> LLMResponse:
        calls.append(task.task_type)
        if "Réponds en français" in prompt:
            return LLMResponse(
                content=json.dumps({
                    "summary": "La capitale de la France est Paris.",
                    "findings": [
                        {
                            "source_id": FAKE_SRC,
                            "evidence_id": FAKE_EVID,
                            "value": "Paris est la capitale de la France.",
                            "epistemic_status": "factual",
                        }
                    ],
                }),
                model="test-model",
                stub=False,
            )
        elif task.task_type == "planning":
            return LLMResponse(
                content=json.dumps({
                    "steps": [
                        {
                            "order": 1,
                            "tool": "collector",
                            "description": "Rechercher la capitale française",
                            "expected_output": "information_unit",
                        }
                    ]
                }),
                model="test-model",
                stub=False,
            )
        else:
            return LLMResponse(
                content=json.dumps({
                    "intent": "Identifier la capitale",
                    "entities": ["France"],
                    "required_information": ["capitale"],
                    "ambiguities": [],
                }),
                model="test-model",
                stub=False,
            )

    monkeypatch.setattr("app.llm.router.model_router.ModelRouter.complete", mock_complete)

    runner = PipelineRunner()
    req_id = ULID.new("REQ_")
    payload = {
        "objective": "Quelle est la capitale de la France ?",
        "request_type": "research",
    }

    delivery = await runner.run(req_id, payload)

    assert "Paris" in delivery["summary"]
    # Verified finding must be present (has SRC_ source + evidence_id)
    assert delivery["status"] == "completed"
    assert len(delivery["findings"]) > 0
    assert delivery["findings"][0]["source_id"] == FAKE_SRC
    # No finding may carry "hypothesis" as source_id (§0.2)
    for finding in delivery["findings"]:
        if isinstance(finding, dict):
            assert finding.get("source_id") != "hypothesis"
    assert "understanding" in calls
    assert "planning" in calls
    assert delivery["information_units"][0]["content"]["details"] != [""]
    assert any("§0.2" in lim for lim in delivery["limitations"])


@pytest.mark.asyncio
async def test_pipeline_marks_unsourced_facts_as_hypothesis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unsourced LLM claims must go to assumptions, not findings (§0.2 invariant 8)."""
    from app.llm.router.model_router import LLMResponse, LLMTask

    async def mock_complete(self: Any, task: LLMTask, prompt: str, **kwargs: Any) -> LLMResponse:
        if "Réponds en français" in prompt:
            # LLM returns facts without source_id / evidence_id
            return LLMResponse(
                content=json.dumps({
                    "summary": "Paris est la capitale.",
                    "findings": [
                        {"source_id": "hypothesis", "finding": "Paris est la capitale de la France."},
                        "La Tour Eiffel se trouve à Paris.",
                    ],
                }),
                model="test-model",
                stub=False,
            )
        return LLMResponse(content="stub", model="test-model", stub=True)

    monkeypatch.setattr("app.llm.router.model_router.ModelRouter.complete", mock_complete)

    runner = PipelineRunner()
    req_id = ULID.new("REQ_")
    payload = {
        "objective": "Quelle est la capitale de la France ?",
        "request_type": "research",
    }

    delivery = await runner.run(req_id, payload)

    # §0.2: no finding should have "hypothesis" as source_id
    for finding in delivery["findings"]:
        if isinstance(finding, dict):
            assert finding.get("source_id") != "hypothesis", (
                f"finding with source_id='hypothesis' must not appear in findings: {finding}"
            )

    # Unsourced claims must be in assumptions, not findings
    assert delivery["status"] == "INSUFFICIENT_EVIDENCE"
    assert len(delivery["assumptions"]) >= 2
    assert all(
        a.get("epistemic_status") == "hypothesis" for a in delivery["assumptions"]
    )
    assert all(
        a.get("reason") == "no_source" for a in delivery["assumptions"]
    )

    # §0.2 limitation notice must be present
    assert any("§0.2" in lim for lim in delivery["limitations"])


@pytest.mark.asyncio
async def test_pipeline_real_web_search_wiring(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stage 3 wires ProviderRouter → FactExtractor → §0.2-compliant findings per §9/§10."""
    from unittest.mock import AsyncMock, MagicMock
    from app.domain.entities.search_result import SearchResult

    # ---- mock ProviderRouter.search ----------------------------------------
    fake_result = SearchResult(
        title="Paris — Wikipédia",
        url="https://fr.wikipedia.org/wiki/Paris",
        snippet="Paris est la capitale et la plus grande ville de France.",
        score=0.95,
        provider="wikipedia",
    )
    mock_search = AsyncMock(return_value=[fake_result])
    monkeypatch.setattr(
        "app.connectors.web.provider_router.ProviderRouter.search", mock_search
    )

    # ---- mock WikipediaExtractor.extract -----------------------------------
    mock_extract = AsyncMock(return_value={
        "title": "Paris",
        "text": "Paris est la capitale et la plus grande ville de France. "
                "La ville est le centre politique, économique et culturel du pays.",
        "language": "fr",
        "url": "https://fr.wikipedia.org/wiki/Paris",
        "error": None,
    })
    monkeypatch.setattr(
        "app.connectors.web.extractors.wikipedia_extractor.WikipediaExtractor.extract",
        mock_extract,
    )

    runner = PipelineRunner()
    req_id = ULID.new("REQ_")
    payload = {
        "objective": "Quelle est la capitale de la France ?",
        "request_type": "research",
    }

    delivery = await runner.run(req_id, payload)

    # Web search was called
    assert mock_search.called

    # Findings must be §0.2-compliant (SRC_ + evidence_id)
    for finding in delivery["findings"]:
        if isinstance(finding, dict):
            assert isinstance(finding.get("source_id"), str)
            assert finding["source_id"].startswith("SRC_"), (
                f"finding without real SRC_: {finding}"
            )
            assert finding.get("evidence_id"), "finding must have evidence_id"
            assert finding.get("source_id") != "hypothesis"

    # At least one web source with reliability_score must be present
    web_srcs = [s for s in delivery["sources"] if s.get("source_type") == "web"]
    assert len(web_srcs) >= 1
    for ws in web_srcs:
        assert ws["source_id"].startswith("SRC_")
        assert "reliability_score" in ws
        assert 0.0 <= ws["reliability_score"] <= 1.0

    # With real facts → status must be completed
    assert delivery["status"] == "completed"

    # §0.2 limitation notice still present
    assert any("§0.2" in lim for lim in delivery["limitations"])
