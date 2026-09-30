"""Router for Information Requests."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import StreamingResponse

from app.api.v1.requests.pipeline_runner import pipeline_runner
from app.api.v1.requests.schemas import (
    InformationRequestCreate,
    InformationRequestResponse,
)
from app.core.errors import InisError
from app.core.statuses import CANCELLED_STATUS
from app.domain.value_objects.ulid import ULID
from app.governance.budget.quotas import GLOBAL_USAGE
from app.knowledge.ingestion.object_intake import intake_source_ref

router = APIRouter(prefix="/requests", tags=["requests"])
usage_router = APIRouter(prefix="/usage", tags=["usage"])

#: Hot path of the runs this process is executing (SSE, live counters).
#:
#: It is **not** the source of truth anymore: the §7 request is also written to
#: the ``requests`` table (revision 0007) and read back from it, so a restart, a
#: rebuild or a second worker no longer erases the history (§41.1). What lives
#: only in this dict is the *live* state of a run — the durable subset is the
#: identity, the objective, the requester, the constraints, the lifecycle status
#: and the resume checkpoint.
_REQUESTS_STORE: dict[str, InformationRequestResponse] = {}

_LOGGER = logging.getLogger(__name__)


async def _persist_request(item: InformationRequestResponse) -> None:
    """Write the durable subset of a new request; never breaks the creation.

    A PostgreSQL outage must not turn "create a request" into an error: the
    request exists in this process either way, and the delivery carries the
    limitation of what could be stored.
    """
    from app.storage.database.engine import get_default_engine
    from app.storage.repositories.request_repository import RequestRepository

    engine = get_default_engine()
    if engine is None:
        return
    try:
        await RequestRepository.create(
            engine,
            {
                "request_id": item.request_id,
                "request_type": item.request_type,
                "objective": item.objective,
                "requester": item.requester,
                "constraints": item.constraints,
                "status": item.status,
                "created_at": item.created_at,
            },
        )
    except Exception:  # noqa: BLE001 - §25.2: an unstored request is still a request
        _LOGGER.warning("request %s not persisted (§7)", item.request_id)


async def _restore_request(request_id: str) -> InformationRequestResponse | None:
    """Rebuild a request from the ``requests`` table, or return ``None``.

    Fields the table does not carry (question, context, required_information,
    required_output, permissions, budget) are left at their defaults instead of
    being invented: the durable subset is what §7 stored, and ``pipeline_state``
    stays ``None`` because the live state of a past run is genuinely gone.
    """
    from app.storage.database.engine import get_default_engine
    from app.storage.repositories.request_repository import RequestRepository

    engine = get_default_engine()
    if engine is None:
        return None
    try:
        row = await RequestRepository.get(engine, request_id)
    except Exception:  # noqa: BLE001 - a degraded read is a 404, not a 500
        _LOGGER.warning("request %s could not be read back (§7)", request_id)
        return None
    if row is None:
        return None
    item = InformationRequestResponse(
        request_id=str(row["request_id"]),
        request_type=str(row["request_type"] or "research"),
        objective=str(row["objective"] or ""),
        requester=row["requester"] or {},
        constraints=row["constraints"] or {},
        status=str(row["status"] or "received"),
        created_at=row["created_at"],
    )
    _REQUESTS_STORE[item.request_id] = item
    return item


async def _known_request(request_id: str) -> InformationRequestResponse | None:
    """Return a known request from memory, or from PostgreSQL (§7)."""
    return _REQUESTS_STORE.get(request_id) or await _restore_request(request_id)


@router.post(
    "",
    response_model=InformationRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new Information Request",
)
async def create_request(
    payload: InformationRequestCreate,
    background_tasks: BackgroundTasks = BackgroundTasks(),
) -> InformationRequestResponse:
    """Create a new information request, trigger the pipeline runner, and return generated request_id.

    When the payload names a ``source_ref`` (§5.2), the object is **ingested
    before** the run is scheduled: the plan must know the document the request
    owns, otherwise the source it named would be invisible to its own run. A
    source that cannot be read is a refusal naming the cause, not a request
    created around a source that does not exist (§25.2).

    Raises:
        HTTPException: 422 when the named source cannot be ingested.
    """
    req_id = ULID.new("REQ_")

    if payload.source_ref:
        try:
            await intake_source_ref(
                request_id=req_id,
                source_ref=payload.source_ref,
                budget=payload.budget,
            )
        except InisError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"Source '{payload.source_ref}' refusée : "
                    f"{type(exc).__name__} — {exc}"
                ),
            ) from exc

    created_at = datetime.now(UTC).isoformat()
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
    await _persist_request(item)

    if background_tasks is not None:
        background_tasks.add_task(pipeline_runner.run, req_id, payload)

    return item


@router.get(
    "/{id}",
    response_model=InformationRequestResponse,
    summary="Get an Information Request by ID",
)
async def get_request(id: str) -> InformationRequestResponse:
    """Retrieve an existing information request by its ID including its latest pipeline state.

    The lookup is memory-first, then PostgreSQL: a request created by another
    worker (or before a restart) is still served, with the status the table
    stored. Its live ``pipeline_state`` is by nature process-local, so a
    restored request reports ``pipeline_state = None`` rather than a state
    nobody observed.
    """
    item = await _known_request(id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Information request '{id}' not found",
        )
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

