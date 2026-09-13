"""Router for Information Units."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status

from app.api.v1.information.schemas import (
    InformationList,
    InformationUnitCreate,
    InformationUnitResponse,
)
from app.domain.value_objects.ulid import ULID

router = APIRouter(prefix="/information", tags=["information"])

_INFORMATION_STORE: dict[str, InformationUnitResponse] = {}


@router.get(
    "",
    response_model=InformationList,
    summary="List information units, optionally filtered by source_id",
)
def list_information(source_id: str | None = None) -> InformationList:
    """Return stored information units, optionally filtered by source_id."""
    units = list(_INFORMATION_STORE.values())
    if source_id is not None:
        units = [u for u in units if u.source_id == source_id]
    return InformationList(units=units, items=units, total=len(units))


@router.post(
    "",
    response_model=InformationUnitResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a new information unit",
)
def create_information(payload: InformationUnitCreate) -> InformationUnitResponse:
    """Record a new information unit and return its generated information_id."""
    info_id = ULID.new("INF_")
    now = datetime.now(timezone.utc).isoformat()
    item = InformationUnitResponse(
        information_id=info_id,
        type=payload.type,
        content=payload.content,
        raw_reference=payload.raw_reference,
        source_id=payload.source_id,
        document_id=payload.document_id,
        dataset_id=payload.dataset_id,
        location=payload.location,
        context=payload.context,
        language=payload.language,
        unit=payload.unit,
        time=payload.time,
        classification=payload.classification,
        quality=payload.quality,
        confidence=payload.confidence,
        provenance=payload.provenance,
        data_stage=payload.data_stage,
        epistemic_status=payload.epistemic_status,
        versions=[info_id],
        created_at=now,
        updated_at=now,
    )
    _INFORMATION_STORE[info_id] = item
    return item


@router.get(
    "/{id}",
    response_model=InformationUnitResponse,
    summary="Get an information unit by ID",
)
def get_information(id: str) -> InformationUnitResponse:
    """Retrieve an existing information unit by its ID or return 404."""
    if id not in _INFORMATION_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Information unit '{id}' not found",
        )
    return _INFORMATION_STORE[id]
