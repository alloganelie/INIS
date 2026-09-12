"""Router for Information Requests."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

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
def create_request(payload: InformationRequestCreate) -> InformationRequestResponse:
    """Create a new information request and return its generated request_id."""
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
    return item


@router.get(
    "/{id}",
    response_model=InformationRequestResponse,
    summary="Get an Information Request by ID",
)
def get_request(id: str) -> InformationRequestResponse:
    """Retrieve an existing information request by its ID or return 404."""
    if id not in _REQUESTS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Information request '{id}' not found",
        )
    return _REQUESTS_STORE[id]
