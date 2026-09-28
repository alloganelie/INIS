"""Router for Agent Registry."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.api.v1.agents.schemas import AgentIdentity

router = APIRouter(prefix="/agents", tags=["agents"])

_AGENTS_STORE: dict[str, AgentIdentity] = {}


@router.get(
    "",
    response_model=list[AgentIdentity],
    summary="List registered agents",
)
def list_agents() -> list[AgentIdentity]:
    """Return all currently registered agents."""
    return list(_AGENTS_STORE.values())


@router.post(
    "/register",
    response_model=AgentIdentity,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new agent",
)
def register_agent(agent: AgentIdentity) -> AgentIdentity:
    """Register or update an agent in the registry."""
    now = datetime.now(timezone.utc).isoformat()
    registered_at = agent.registered_at or now
    last_seen_at = agent.last_seen_at or now
    stored_agent = agent.model_copy(
        update={"registered_at": registered_at, "last_seen_at": last_seen_at}
    )
    _AGENTS_STORE[agent.agent_id] = stored_agent
    return stored_agent


@router.get(
    "/{id}",
    response_model=AgentIdentity,
    summary="Get an agent by ID",
)
def get_agent(id: str) -> AgentIdentity:
    """Retrieve an agent by ID or return 404."""
    if id not in _AGENTS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{id}' not found",
        )
    return _AGENTS_STORE[id]


@router.get(
    "/{agent_id}/schema",
    summary="Get JSON Schema specification for an agent per §41.15",
)
def get_agent_schema(agent_id: str) -> dict[str, Any]:
    """Return input and output JSON schemas for the registered agent."""
    agent = _AGENTS_STORE.get(agent_id)
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found in registry",
        )

    # If schemas are empty on the registered agent, provide default JSON Schemas per §41.15
    input_schemas = agent.input_schemas
    if not input_schemas:
        input_schemas = [
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "title": f"{agent.name}Input",
                "type": "object",
                "properties": {
                    "request_id": {"type": "string"},
                    "task": {"type": "string"},
                    "parameters": {"type": "object"},
                },
                "required": ["request_id", "task"],
            }
        ]

    output_schemas = agent.output_schemas
    if not output_schemas:
        output_schemas = [
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "title": f"{agent.name}Output",
                "type": "object",
                "properties": {
                    "request_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["completed", "failed", "degraded"]},
                    "result": {"type": "object"},
                },
                "required": ["request_id", "status"],
            }
        ]

    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "version": agent.version,
        "input_schemas": input_schemas,
        "output_schemas": output_schemas,
    }
