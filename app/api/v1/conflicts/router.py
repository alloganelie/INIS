"""Router for Conflicts per §14.3 and §32."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.v1.conflicts.schemas import (
    ConflictCreate,
    ConflictList,
    ConflictResponse,
)
from app.core.time import utc_now
from app.domain.value_objects.ulid import ULID
from app.storage.repositories.conflict_repository import (
    ConflictRepository,
    get_database_engine,
)

router = APIRouter(prefix="/conflicts", tags=["conflicts"])

_CONFLICTS_STORE: dict[str, ConflictResponse] = {}


@router.get(
    "",
    response_model=ConflictList,
    summary="List conflicts, optionally filtered by status",
)
async def list_conflicts(status: str | None = None) -> ConflictList:
    """Return stored conflicts, optionally filtered by status."""
    engine = get_database_engine()
    if engine is not None:
        data = await ConflictRepository.list(engine, status=status)
        items = [ConflictResponse(**d) for d in data]
        return ConflictList(items=items, conflicts=items, total=len(items))

    items = list(_CONFLICTS_STORE.values())
    if status is not None:
        target_status = status.lower()
        items = [
            c
            for c in items
            if c.status.lower() == target_status or c.resolution_status.lower() == target_status
        ]
    return ConflictList(items=items, conflicts=items, total=len(items))


@router.post(
    "",
    response_model=ConflictResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Record a detected conflict",
)
async def create_conflict(payload: ConflictCreate) -> ConflictResponse:
    """Record a new conflict and return its generated conflict_id."""
    conflict_id = ULID.new("CONFLICT_")
    now = utc_now().isoformat()
    status_val = payload.status or payload.resolution_status or "open"
    conflict_dict = {
        "conflict_id": conflict_id,
        "information_a": payload.information_a,
        "information_b": payload.information_b,
        "information_ids": payload.information_ids,
        "claim_ids": payload.claim_ids,
        "difference_type": payload.difference_type,
        "severity": payload.severity,
        "status": status_val,
        "resolution_status": status_val,
        "description": payload.description,
        "resolution_evidence": payload.resolution_evidence,
        "detected_at": now,
    }

    engine = get_database_engine()
    if engine is not None:
        saved = await ConflictRepository.create(engine, conflict_dict)
        item = ConflictResponse(**saved)
        _CONFLICTS_STORE[conflict_id] = item
        return item

    item = ConflictResponse(**conflict_dict)
    _CONFLICTS_STORE[conflict_id] = item
    return item


@router.get(
    "/{id}",
    response_model=ConflictResponse,
    summary="Get a conflict by ID",
)
async def get_conflict(id: str) -> ConflictResponse:
    """Retrieve an existing conflict by its ID or return 404."""
    engine = get_database_engine()
    if engine is not None:
        saved = await ConflictRepository.get(engine, id)
        if saved is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conflict '{id}' not found",
            )
        return ConflictResponse(**saved)

    if id not in _CONFLICTS_STORE:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conflict '{id}' not found",
        )
    return _CONFLICTS_STORE[id]

