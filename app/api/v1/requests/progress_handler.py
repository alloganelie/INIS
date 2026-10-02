"""Progress and resume handler for long-running Information Requests per §41.1."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.agents.runtime.lifecycle import GRACEFUL_EXPIRY_STATUS, InvalidResumeToken
from app.api.v1.requests.pipeline_runner import PIPELINE_STEPS_TOTAL, pipeline_runner
from app.api.v1.requests.router import _REQUESTS_STORE

router = APIRouter(prefix="/requests", tags=["requests"])


class RequestProgress(BaseModel):
    """Progress snapshot for an in-flight or completed Information Request."""

    steps_total: int
    steps_done: int
    current_step: str
    estimated_completion: str | None = None
    partial_findings_available: bool


class ResumeRequest(BaseModel):
    """Payload to resume an interrupted Information Request (§41.1)."""

    resume_token: str = Field(..., min_length=8, description="Opaque token from a prior run")


class ResumeState(BaseModel):
    """Resume projection of an Information Request (§41.1)."""

    resumable: bool
    last_committed_step: str | None = None
    last_committed_at: str | None = None
    resume_token: str


class ResumeResponse(BaseModel):
    """Result of a successful resume operation (§41.1)."""

    request_id: str
    status: str
    last_committed_step: str | None = None
    resumable: bool
    steps_done: int
    steps_total: int


@router.get(
    "/{id}/progress",
    response_model=RequestProgress,
    summary="Get progress of an Information Request",
)
async def get_request_progress(id: str) -> RequestProgress:
    """Return the current execution progress of an information request.

    The snapshot is read from the real :class:`RequestLifecycle` maintained by
    the pipeline runner (§41.1) instead of being derived from the request
    status. Requests that never entered the pipeline fall back to the
    nominal §28 step count so callers always get a coherent payload.

    §41.1 — la progression est aussi **persistée** (table ``progress``, écrite au
    même moment que le point de reprise). Quand l'état en mémoire a disparu —
    redémarrage du worker, autre processus, requête servie par une autre
    instance — la dernière projection connue est relue en base plutôt que
    d'inventer un état ou de renvoyer un 404 sur une requête qui existe.
    """
    expired = pipeline_runner.collect_expired(id)
    if expired is not None:
        return RequestProgress(
            steps_total=expired["steps_total"],
            steps_done=expired["steps_done"],
            current_step=expired["status"],
            estimated_completion=expired["expired_at"],
            partial_findings_available=bool(expired["findings"]),
        )

    snapshot = pipeline_runner.progress(id)
    if snapshot is not None:
        return RequestProgress(**snapshot.to_dict())

    if id in _REQUESTS_STORE:
        return _progress_from_status(_REQUESTS_STORE[id])

    persisted = await _persisted_progress(id)
    if persisted is not None:
        return RequestProgress(**persisted)

    if await _request_exists(id):
        # La requête existe mais n'a jamais produit de progression : l'état
        # initial est dit tel quel, jamais un état avancé inventé.
        return RequestProgress(
            steps_total=PIPELINE_STEPS_TOTAL,
            steps_done=0,
            current_step="RECEIVING",
            estimated_completion=None,
            partial_findings_available=False,
        )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Information request '{id}' not found",
    )


def _progress_from_status(req: Any) -> RequestProgress:
    """Derive the nominal progress of a request that never entered the pipeline."""
    steps_done = 0
    current_step = "RECEIVING"
    if req.status == "processing":
        steps_done = 1
        current_step = "UNDERSTANDING"
    elif req.status not in ("received", "queued"):
        steps_done = PIPELINE_STEPS_TOTAL
        current_step = "DELIVERY"
    return RequestProgress(
        steps_total=PIPELINE_STEPS_TOTAL,
        steps_done=steps_done,
        current_step=current_step,
        estimated_completion=None,
        partial_findings_available=steps_done > 0,
    )


async def _persisted_progress(id: str) -> dict[str, Any] | None:
    """Read the last persisted progress of *id*, or ``None`` (§41.1)."""
    from app.storage.repositories.information_unit_repository import get_database_engine
    from app.storage.repositories.progress_repository import ProgressRepository

    engine = get_database_engine()
    if engine is None:
        return None
    try:
        return await ProgressRepository.get(engine, id)
    except Exception:  # noqa: BLE001 - a progress gap must not fail the endpoint
        return None


async def _request_exists(id: str) -> bool:
    """Return whether *id* is a known request, in memory or in PostgreSQL."""
    from app.storage.repositories.information_unit_repository import get_database_engine
    from app.storage.repositories.request_repository import RequestRepository

    if id in _REQUESTS_STORE:
        return True
    engine = get_database_engine()
    if engine is None:
        return False
    try:
        return await RequestRepository.get(engine, id) is not None
    except Exception:  # noqa: BLE001 - an unreadable database is not a 500 here
        return False


@router.get(
    "/{id}/resume",
    response_model=ResumeState,
    summary="Get the resume state of an interrupted request (opaque token) per §41.1",
)
def get_resume_state(id: str) -> ResumeState:
    """Return the last committed step and an opaque resume token."""
    if id not in _REQUESTS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Information request '{id}' not found",
        )
    state = pipeline_runner.resume_state(id)
    if state is None:
        # The request never started: there is no checkpoint to resume from.
        lifecycle = pipeline_runner.register_lifecycle(id)
        state = lifecycle.resume_state()
    return ResumeState(**state)


@router.post(
    "/{id}/resume",
    response_model=ResumeResponse,
    status_code=status.HTTP_200_OK,
    summary="Resume an interrupted Information Request per §41.1",
)
def resume_request(id: str, payload: ResumeRequest) -> ResumeResponse:
    """Resume an interrupted request from its last committed step."""
    if id not in _REQUESTS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Information request '{id}' not found",
        )
    try:
        result: dict[str, Any] = pipeline_runner.resume(id, payload.resume_token)
    except InvalidResumeToken as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return ResumeResponse(**result)


@router.post(
    "/{id}/expire",
    response_model=dict,
    summary="Deliver the partial result of an expired request (graceful expiry) per §41.1",
)
def expire_request(id: str) -> dict[str, Any]:
    """Force the graceful expiry path and return the PARTIAL_SUCCESS payload."""
    if id not in _REQUESTS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Information request '{id}' not found",
        )
    lifecycle = pipeline_runner.get_lifecycle(id) or pipeline_runner.register_lifecycle(id)
    payload = lifecycle.expire_gracefully()
    payload["status"] = GRACEFUL_EXPIRY_STATUS
    return payload

