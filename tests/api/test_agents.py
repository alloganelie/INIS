"""Tests for Agent Registry endpoints."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_list_agents() -> None:
    """Ensure GET /v1/agents returns a list."""
    response = client.get("/v1/agents")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_register_agent() -> None:
    """Ensure POST /v1/agents/register registers a new agent."""
    payload = {
        "agent_id": "agent_codex",
        "name": "Codex Agent",
        "description": "Autonomous planning and synthesis",
        "version": "0.1.0",
        "capabilities": ["planning", "domain_reasoning"],
    }
    response = client.post("/v1/agents/register", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["agent_id"] == payload["agent_id"]
    assert data["name"] == payload["name"]
    assert data["status"] == "available"
    assert "registered_at" in data
    assert data["registered_at"] is not None


def test_list_agents_contains_registered_agent() -> None:
    """Ensure newly registered agent appears in GET /v1/agents."""
    payload = {
        "agent_id": "agent_opencode",
        "name": "OpenCode Messaging Agent",
        "version": "0.1.0",
    }
    register_res = client.post("/v1/agents/register", json=payload)
    assert register_res.status_code == 201

    list_res = client.get("/v1/agents")
    assert list_res.status_code == 200
    agents = list_res.json()
    registered_ids = [a["agent_id"] for a in agents]
    assert "agent_opencode" in registered_ids
