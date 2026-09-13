"""Progress handler for long-running Information Requests per §41.1."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.v1.requests.router import _REQUESTS_STORE

router = APIRouter(prefix="/requests", tags=["requests"])


class RequestProgress(BaseModel):
    """Progress snapshot for an in-flight or completed Information Request."""

    steps_total: int
    steps_done: int
    current_step: str
    estimated_completion: str | None = None
    partial_findings_available: bool


@router.get(
    "/{id}/progress",
    response_model=RequestProgress,
    summary="Get progress of an Information Request",
)
def get_request_progress(id: str) -> RequestProgress:
    """Return the current execution progress of an information request.

    The in-memory store holds no live execution state — the handler
    derives a synthetic snapshot from the stored request so callers can
    poll without error.  Actual step tracking will be wired to the
    planning/execution layer in a later phase.
    """
    if id not in _REQUESTS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Information request '{id}' not found",
        )

    req = _REQUESTS_STORE[id]

    # Derive a deterministic snapshot from the stored request status.
    status_value = req.status
    if status_value in ("received", "queued"):
        steps_done = 0
        current_step = "RECEIVING"
        estimated_completion = None
        partial_available = False
    elif status_value == "processing":
        steps_done = 5
        current_step = "DATA_ACQUISITION"
        estimated_completion = None
        partial_available = True
    else:
        # completed, cancelled, error, etc.
        steps_done = 28
        current_step = "DONE"
        estimated_completion = None
        partial_available = True

    return RequestProgress(
        steps_total=28,
        steps_done=steps_done,
        current_step=current_step,
        estimated_completion=estimated_completion,
        partial_findings_available=partial_available,
    )
