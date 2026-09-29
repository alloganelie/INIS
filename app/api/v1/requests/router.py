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
from app.core.statuses import CANCELLED_STATUS
from app.governance.budget.quotas import GLOBAL_USAGE

router = APIRouter(prefix="/requests", tags=["requests"])
usage_router = APIRouter(prefix="/usage", tags=["usage"])

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
        budget=payload.budget,
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


@router.post(
    "/{id}/cancel",
    response_model=InformationRequestResponse,
    summary="Cancel an Information Request (§32)",
)
def cancel_request(id: str) -> InformationRequestResponse:
    """Cancel a request and return its updated state (§1.3 ``CANCELLED``).

    Cancellation is idempotent: cancelling an already-cancelled request returns
    the same state instead of failing, so a client retry after a timeout is
    safe. An unknown request is a 404, never a silent success.
    """
    if id not in _REQUESTS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Information request '{id}' not found",
        )
    item = _REQUESTS_STORE[id]
    state = pipeline_runner.cancel(id)
    item.status = str(state.get("status") or CANCELLED_STATUS)
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


@router.get(
    "/{id}/usage",
    summary="Get the §41.2 consumption report of a request",
)
def get_request_usage(id: str) -> dict[str, Any]:
    """Return the ``usage_report`` of one Information Request (§41.2)."""
    if id not in _REQUESTS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Information request '{id}' not found",
        )
    report = pipeline_runner.usage_report(id)
    if report is None:
        report = pipeline_runner.guard_for(id).report()
    return report


@router.get(
    "/{id}/llm-traces",
    summary="Get the §41.12 LLM decision traces of a request",
)
def get_request_llm_traces(id: str) -> dict[str, Any]:
    """Return every ``llm_decision_trace`` recorded for one Information Request.

    Traces expose the sha256 digest of each prompt, never the prompt itself.
    """
    if id not in _REQUESTS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Information request '{id}' not found",
        )
    traces = pipeline_runner.llm_traces(id)
    return {"request_id": id, "count": len(traces), "traces": traces}


@usage_router.get(
    "/global",
    summary="Get the aggregated §41.2 consumption across all requests",
)
def get_global_usage() -> dict[str, Any]:
    """Return the aggregated consumption of every tracked request (§41.2)."""
    return GLOBAL_USAGE.global_report()

