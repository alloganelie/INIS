"""Router for Information Requests."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.v1.requests.pipeline_runner import pipeline_runner
from app.api.v1.requests.schemas import (
    InformationRequestCreate,
    InformationRequestResponse,
)
from app.domain.value_objects.ulid import ULID

router = APIRouter(prefix="/requests", tags=["requests"])

_REQUESTS_STORE: dict[str, InformationRequestResponse] = {}


@router.post(
    "",
    response_model=InformationRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Information Request",
)
def create_request(
    payload: InformationRequestCreate,
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> InformationRequestResponse:
    """Create a new information request, trigger the pipeline runner, and return generated request_id."""
    req_id = ULID.new("REQ_")
    created_at = datetime.now(timezone.utc).isoformat()
    item = InformationRequestResponse(
        request_id=req_id,
        request_type=payload.request_type,
        objective=payload.objective,
        question=payload.question,
        context=payload.context,
        required_information=payload.required_information,
        constraints=payload.constraints,
        required_output=payload.required_output,
        requester=payload.requester,
        permissions=payload.permissions,
        status="received",
        created_at=created_at,
    )
    _REQUESTS_STORE[req_id] = item

    if background_tasks is not None:
        background_tasks.add_task(pipeline_runner.run, req_id, payload)

    return item


@router.get(
    "/{id}",
    response_model=InformationRequestResponse,
    summary="Get an Information Request by ID",
)
def get_request(id: str) -> InformationRequestResponse:
    """Retrieve an existing information request by its ID including its latest pipeline state."""
    if id not in _REQUESTS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Information request '{id}' not found",
        )
    item = _REQUESTS_STORE[id]
    state = pipeline_runner.get_state(id)
    if state:
        item.status = state.get("status", item.status)
        item.pipeline_state = state
    return item


@router.get(
    "/{id}/events",
    summary="Stream pipeline execution events via SSE",
)
async def get_request_events(id: str) -> StreamingResponse:
    """Stream Server-Sent Events (SSE) for the request pipeline execution."""
    if id not in _REQUESTS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Information request '{id}' not found",
        )
    return StreamingResponse(
        pipeline_runner.event_stream(id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
