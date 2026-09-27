"""Tests for §41.15 OpenAPI, JSON Schema and Changelog."""

from __future__ import annotations

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_openapi_json_accessible():
    res = client.get("/v1/openapi.json")
    assert res.status_code == 200
    data = res.json()
    assert "openapi" in data
    # FastAPI outputs OpenAPI 3.1.x
    assert data["openapi"].startswith("3.1")
    assert "info" in data
    assert "paths" in data
    # Verify core domain paths are mounted
    paths = data["paths"]
    assert "/v1/requests" in paths
    assert "/v1/agents" in paths
    assert "/v1/agents/{agent_id}/schema" in paths
    assert "/v1/sources" in paths
    assert "/v1/health" in paths
    assert "/v1/changelog" in paths


def test_agent_schema_endpoint():
    # 1. Register an agent
    reg_payload = {
        "agent_id": "AGT_SCHEMA_TEST",
        "name": "SchemaTestAgent",
        "description": "Agent with schemas",
        "version": "1.0.0",
        "input_schemas": [
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            }
        ],
        "output_schemas": [
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {"answer": {"type": "string"}},
            }
        ],
    }
    reg = client.post("/v1/agents/register", json=reg_payload)
    assert reg.status_code == 201

    # 2. Query schema
    schema_res = client.get("/v1/agents/AGT_SCHEMA_TEST/schema")
    assert schema_res.status_code == 200
    schema_data = schema_res.json()
    assert schema_data["agent_id"] == "AGT_SCHEMA_TEST"
    assert len(schema_data["input_schemas"]) == 1
    assert schema_data["input_schemas"][0]["properties"]["query"]["type"] == "string"
    assert len(schema_data["output_schemas"]) == 1

    # 3. 404 for unknown agent
    unknown = client.get("/v1/agents/NONEXISTENT/schema")
    assert unknown.status_code == 404


def test_changelog_endpoint():
    res = client.get("/v1/changelog")
    assert res.status_code == 200
    data = res.json()
    assert "version" in data
    assert data["version"] == "2.0.0"
    assert "phases" in data
    phases = data["phases"]
    assert len(phases) >= 10
    phase_names = [p["name"] for p in phases]
    assert "PHASE-01" in phase_names
    assert "PHASE-11" in phase_names
