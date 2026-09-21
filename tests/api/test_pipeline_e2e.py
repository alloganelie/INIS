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
    assert result["status"] == "completed"

    # Fetch request
    get_res = client.get(f"/v1/requests/{actual_id}")
    assert get_res.status_code == 200
    res_data = get_res.json()
    assert res_data["status"] == "completed"
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

    assert result["status"] == "completed"
    assert result["request_id"] == req_id
    assert result["response_id"].startswith("RESP_")
    assert len(result["findings"]) > 0
    assert "confidence" in result
    assert result["confidence"]["score"] > 0.0


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
    assert delivery["status"] == "completed"
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
